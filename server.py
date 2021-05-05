import socket
import threading
import tiles
import selectors
import types
import random
import time
import copy
import numpy as np

WAITTIME = 10
SLEEPTIME = 1

class Socket:
    """
    Holds data for each socket connection.
    """
    name = ''
    socketID = None
    currentTiles = [None, None, None, None]
    active = False

    def __init__(self, socketID, name):
        self.socketID = socketID
        self.name = name
        self.active = True
        self.currentTiles = [None, None, None, None]


class Gamestats:
    """
    Holds data for currently running game.
    """
    activePlayers = []
    eliminatedPlayers = []
    placedTiles = []
    tokenMoves = []
    startingPlayers = []
    timeoutTimer = threading.Timer(WAITTIME, None)
    currentTurnId = None

    def __init__(self, activePlayers, currentTurnId):
        self.activePlayers = activePlayers
        self.currentTurnId = currentTurnId
        self.placedTiles.clear()
        self.tokenMoves.clear()
        self.eliminatedPlayers.clear()
        self.startingPlayers.clear()


#global variables
connectedClients = np.empty(tiles.IDNUM_LIMIT, dtype=object)
board = tiles.Board()
latestID = -1
gameRunning = False
game = None


# create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# listen on all network interfaces
server_address = ('', 30020)
sock.bind(server_address)
print("Listening on {}.".format(sock.getsockname()))

# have a maximum backlog of 5 clients
sock.listen(5)
sock.setblocking(False)

# allow high level I/O multiplexing
sel = selectors.DefaultSelector()
sel.register(sock, selectors.EVENT_READ, data=None)




def place_tile(msg):
    """
    Executes tile placement and sends updated board to all active connections. 
    Msg expected in form [msg.idnum, msg.tileid, msg.rotation,msg.x, msg.y].
    """
    # update placement for all connections
    send_to_all(tiles.MessagePlaceTile(
        msg[0], msg[1], msg[2], msg[3], msg[4]).pack())
    game.placedTiles.append(msg)

    # pickup a new tile
    tileid = tiles.get_random_tileid()
    connectedClients[msg[0]].socketID.send(
        tiles.MessageAddTileToHand(tileid).pack())

    # update tile info 
    for index, tile in enumerate(connectedClients[msg[0]].currentTiles):
        if(msg[1] == tile):
            connectedClients[msg[0]].currentTiles[index] = tileid
            break
    update_tokens()


def update_tokens():
    """
    Updates tokens for all active players and sends updated positions to all active connections.
    """

    game.timeoutTimer.cancel()

    #check for token movement
    positionupdates, eliminated = board.do_player_movement(game.activePlayers)

    #apply updates
    for msg in positionupdates:
        game.tokenMoves.append([msg.idnum, msg.x, msg.y, msg.position])
        send_to_all(tiles.MessageMoveToken(
            msg.idnum, msg.x, msg.y, msg.position).pack())

    #apply eliminations
    for idnum in game.activePlayers:
        if idnum in eliminated:
            print("Player Eliminated:", idnum)
            send_to_all(tiles.MessagePlayerEliminated(idnum).pack())
            game.eliminatedPlayers.append(idnum)
            for index, elim in enumerate(game.activePlayers):
                if(idnum == elim and index <= game.currentTurnId):
                    game.currentTurnId -= 1
            game.activePlayers.remove(idnum)

    next_turn()



def send_to_all(msg):
    """
    Sends 'msg' to all active connections. Returns an array with the idnums of all active connections.
    If 'msg' is None, no messages are sent but still returns array of idnums.
    """
    numberActive = []
    numberActive.clear()
    for idnum in range(len(connectedClients)):
        if(connectedClients[idnum] is not None):
            if(msg is not None and connectedClients[idnum].active):
                numberActive.append(idnum)
                connectedClients[idnum].socketID.send(msg)
            elif(connectedClients[idnum].active):
                numberActive.append(idnum)
        else:
            return numberActive

def update_player():
    """
    Updates most recently connected player on the gamestate. Sends player joined messages regarding
    all active clients. If a game is running, all game state changes are sent to player aswell.
    """
    connection = connectedClients[latestID].socketID

    # inform new player of existing players
    for index in range(len(connectedClients)):
        if(connectedClients[index] is not None):
            connection.send(tiles.MessagePlayerJoined(connectedClients[index].name, index).pack())
        else:
            break

    if(gameRunning):
        print("new client")
        # notify player of the id number of all players that started in the current game
        for player in game.startingPlayers: 
            connection.send(tiles.MessagePlayerTurn(player).pack())
        # notify player of all token positions 
        for tile in game.placedTiles:  
            connection.send(tiles.MessagePlaceTile(
                tile[0], tile[1], tile[2], tile[3], tile[4]).pack())
        # notify player of all tiles that are already on the board
        for token in game.tokenMoves:  
            connection.send(tiles.MessageMoveToken(
                token[0], token[1], token[2], token[3]).pack())
        # notify the client of all players that have been eliminated from the current game
        for player in game.eliminatedPlayers:
            connection.send(tiles.MessagePlayerEliminated(player).pack())
            
        # if a game is running, notify the client of the real current turn
        connection.send(tiles.MessagePlayerTurn(
            game.activePlayers[game.currentTurnId]).pack())



def timeout():
    """
    Called when a player takes too long to make a manual input move. 
    Makes a random (legitimate) move for them.
    """
    #msg in form [msg.idnum, msg.tileid, msg.rotation,msg.x, msg.y]
    print("TIMEOUT!")
    idnum = game.activePlayers[game.currentTurnId]
    
    if(not board.have_player_position(idnum)):  # if no token
        for tile in game.placedTiles:  # check to see whether tile has been placed
            if(tile[0] == idnum):
                while(True):
                    if(board.set_player_start_position(idnum, tile[3], tile[4], random.randint(0, 7))):
                        update_tokens()
                        return
        while(True):  # if not tile has been placed
            msg = [idnum, connectedClients[idnum].currentTiles[random.randint(0, 3)], random.randint(0, 3), random.randrange(
                0, tiles.BOARD_WIDTH), random.randrange(0, tiles.BOARD_HEIGHT)]

            if(board.set_tile(msg[3], msg[4], msg[1], msg[2], msg[0])):
                place_tile(msg)
                return

    if(board.have_player_position(idnum)):
        x, y, d = board.get_player_position(idnum)
        while(True):
            msg = [idnum, connectedClients[idnum].currentTiles[random.randint(
                0, 3)], random.randint(0, 3), x, y]
            if(board.set_tile(msg[3], msg[4], msg[1], msg[2], msg[0])):
                place_tile(msg)
                return


def make_move(buffer):
    """
    Called when a player makes a manual input move (adding a tile or chosing a token).
    Reads message from bytearray and checks its a legitimate move, if it is then board is updated.
    """
    while True:
        msg, consumed = tiles.read_message_from_bytearray(buffer)
        if not consumed:
            break
        buffer = buffer[consumed:]

        # sent by the player to put a tile onto the board (in all turns except
        # their second)
        if isinstance(msg, tiles.MessagePlaceTile):
            if(board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum)):
                place_tile([msg.idnum, msg.tileid, msg.rotation, msg.x, msg.y])

        # sent by the player in the second turn, to choose their token's
        # starting path
        elif isinstance(msg, tiles.MessageMoveToken):
            if(not board.have_player_position(msg.idnum)):
                if(board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position)):
                    update_tokens()







def next_turn():
    """
    Called each time player whos turn it is finishes 'making' a move (through input, timeout or disconnection).
    Updates currentTurnID and restarts timer for the next player. If prevous game finished, chooses to start a new
    game (if connections >=2) or sets gameRunning to false.
    """
    global game
    global gameRunning

    game.timeoutTimer.cancel()
    game.timeoutTimer = threading.Timer(WAITTIME, timeout)

    if(len(game.activePlayers) >= 2):  # if enough players that game can continue; continue playing
        # if at the end of the array next position is 0
        if(game.currentTurnId == len(game.activePlayers)-1):
            game.currentTurnId = 0
        else:
            game.currentTurnId += 1
        game.timeoutTimer.start()
        send_to_all(tiles.MessagePlayerTurn(
            game.activePlayers[game.currentTurnId]).pack())
        print("Move complete, next move by id:", game.activePlayers[game.currentTurnId])
    elif(len(send_to_all(None)) >= 2):  # else if enough players to start a new game; start new game
        new_game()

    else:  # if not enough players to start a new game
        print("\nGame Finished")
        board.reset()
        gameRunning = False


def new_game():
    """
    Starts a new game for connected clients. Chooses randomly from the currently connected clients
    if number of clients > 4. Sets a random turn order for those chosen clients and gives each client
    a random selection of tiles. If game was prevously running, board and gamestate reset.
    """
    global gameRunning
    global game
    print("\nNew Game Started!")
    send_to_all(tiles.MessageCountdown().pack())
    time.sleep(SLEEPTIME)
    board.reset()
    gameRunning = True
    # chooses random idnums from all active connections
    sample = random.sample(send_to_all(None), min(
        len(send_to_all(None)), tiles.PLAYER_LIMIT))
    turn = random.randrange(0, len(sample))
    game = Gamestats(sample, turn)
    send_to_all(tiles.MessageGameStart().pack())


    for idnum in game.activePlayers:
        game.startingPlayers.append(idnum)
        send_to_all(tiles.MessagePlayerTurn(idnum).pack())
    
    print("Idnums in current game:",game.startingPlayers)

    for idnum in game.activePlayers:
        for index in range(tiles.HAND_SIZE):
            tileid = tiles.get_random_tileid()
            connectedClients[idnum].currentTiles[index] = tileid
            connectedClients[idnum].socketID.send(
                tiles.MessageAddTileToHand(tileid).pack())

    next_turn()

def accept_new_connection(sock):
    """
    Handles new connections as recieved by socket. Registers new client in both local server
    variables as well as selection register.
    """
    global latestID
    connection, addr = sock.accept()
    host, port = addr
    name = '{}:{}'.format(host, port)
    connection.setblocking(False)
    data = types.SimpleNamespace(addr=addr, inb=b'', outb=b'')
    events = selectors.EVENT_READ
    sel.register(connection, events, data=data)
    latestID += 1
    print('Received connection from client {}.'.format(latestID))
    connection.send(tiles.MessageWelcome(
        latestID).pack())  # welcome new player
    send_to_all(tiles.MessagePlayerJoined(
        name, latestID).pack())  # send everyone new player info
    # add new player to connectedClients
    connectedClients[latestID] = Socket(connection, name)
    update_player()

    if(not gameRunning and len(send_to_all(None)) >= 2):
        new_game()

def accept_client_data(key, mask):
    """
    Handles new data as recieved by socket from prevously registered clients. If the data sent
    is from client whos turn it is it is added to the processing buffer, else is ignored.
    If data is empty, client has disconnected and server variables are updated accordingly.
    """
    sock = key.fileobj
    data = key.data
    if mask & selectors.EVENT_READ:
        chunk = sock.recv(4096)  # Should be ready to read
        if not chunk:
            sel.unregister(sock)
            sock.close()
            for idnum in range(len(connectedClients)):
                if(sock == connectedClients[idnum].socketID):
                    print('Client {} disconnected.'.format(idnum))
                    connectedClients[idnum].active = False
                    if(gameRunning):
                        # if was a player in current game
                        if(idnum in game.activePlayers):
                            send_to_all(
                                tiles.MessagePlayerEliminated(idnum).pack())
                            # was the disconnected players turn
                            if(game.activePlayers[game.currentTurnId] == idnum):
                                game.timeoutTimer.cancel()
                                game.currentTurnId -= 1
                            else:  # correct current run index if player removed was before it
                                for index, playerID in enumerate(game.activePlayers):
                                    if(idnum == playerID and index < game.currentTurnId):
                                        game.currentTurnId -= 2
                                    elif(idnum == playerID):
                                        game.currentTurnId -= 1
                            game.activePlayers.remove(idnum)
                            send_to_all(tiles.MessagePlayerLeft(idnum).pack())
                            next_turn()
                        # wasnt part of the game
                       # send_to_all(tiles.MessagePlayerLeft(idnum).pack())
                    return

            return

        buffer = bytearray()
        buffer.extend(chunk)
        if(sock == connectedClients[game.activePlayers[game.currentTurnId]].socketID and gameRunning):
            make_move(buffer)






# infinite loop checking socket for incoming packages
while True:
    events = sel.select(timeout=None)
    for key, mask in events:
        if key.data is None:
            # if no data; must be a new client connection
            accept_new_connection(key.fileobj)
        else:
            # with data; exsiting client connection
            accept_client_data(key, mask)
