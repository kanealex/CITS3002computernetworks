import socket
import threading
import tiles
import selectors
import types
import random
import time
import copy
import numpy as np

WAITTIME = 10 #waittime till auto move
SLEEPTIME = 0 #sleep time between games

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


class Server:

    def __init__(self, host, port):
        self.connectedClients = np.empty(tiles.IDNUM_LIMIT, dtype=object)
        self.board = tiles.Board()
        self.latestID = -1
        self.gameRunning = False
        self.game = None
        self.host = host
        self.port = port
        self.sel = selectors.DefaultSelector()

    def place_tile(self, msg):
        """
        Executes tile placement and sends updated board to all active connections. 
        Msg expected in form [msg.idnum, msg.tileid, msg.rotation,msg.x, msg.y].
        """
        # update placement for all connections
        self.send_to_all(tiles.MessagePlaceTile(
            msg[0], msg[1], msg[2], msg[3], msg[4]).pack())
        self.game.placedTiles.append(msg)

        # pickup a new tile
        tileid = tiles.get_random_tileid()
        self.connectedClients[msg[0]].socketID.send(
            tiles.MessageAddTileToHand(tileid).pack())

        # update tile info
        for index, tile in enumerate(self.connectedClients[msg[0]].currentTiles):
            if(msg[1] == tile):
                self.connectedClients[msg[0]].currentTiles[index] = tileid
                break
        self.update_tokens()

    def update_tokens(self):
        """
        Updates tokens for all active players and sends updated positions to all active connections.
        """
        self.game.timeoutTimer.cancel()

        # check for token movement
        positionupdates, eliminated = self.board.do_player_movement(
            self.game.activePlayers)

        # apply updates
        for msg in positionupdates:
            self.game.tokenMoves.append(
                [msg.idnum, msg.x, msg.y, msg.position])
            self.send_to_all(tiles.MessageMoveToken(
                msg.idnum, msg.x, msg.y, msg.position).pack())

        # apply eliminations
        for idnum in self.game.activePlayers:
            if idnum in eliminated:
                print("Player Eliminated:", idnum)
                self.send_to_all(tiles.MessagePlayerEliminated(idnum).pack())
                self.game.eliminatedPlayers.append(idnum)
                for index, elim in enumerate(self.game.activePlayers):
                    if(idnum == elim and index <= self.game.currentTurnId):
                        self.game.currentTurnId -= 1


                self.game.activePlayers.remove(idnum)

        self.next_turn()

    def send_to_all(self, msg):
        """
        Sends 'msg' to all active connections. Returns an array with the idnums of all active connections.
        If 'msg' is None, no messages are sent but still returns array of idnums.
        """
        numberActive = []
        numberActive.clear()
        for idnum in range(len(self.connectedClients)):
            if(self.connectedClients[idnum] is not None):
                if(msg is not None and self.connectedClients[idnum].active):
                    numberActive.append(idnum)
                    self.connectedClients[idnum].socketID.send(msg)
                elif(self.connectedClients[idnum].active):
                    numberActive.append(idnum)
            else:
                return numberActive

    def update_player(self):
        """
        Updates most recently connected player on the gamestate. Sends player joined messages regarding
        all active clients. If a self.game is running, all self.game state changes are sent to player aswell.
        """
        connection = self.connectedClients[self.latestID].socketID

        # inform new player of existing players
        for index in range(len(self.connectedClients)):
            if(self.connectedClients[index] is not None):
                connection.send(tiles.MessagePlayerJoined(
                    self.connectedClients[index].name, index).pack())
            else:
                break

        if(self.gameRunning):
            print("new client")
            # notify player of the id number of all players that started in the current self.game
            for player in self.game.startingPlayers:
                connection.send(tiles.MessagePlayerTurn(player).pack())
            # notify player of all token positions
            for tile in self.game.placedTiles:
                connection.send(tiles.MessagePlaceTile(
                    tile[0], tile[1], tile[2], tile[3], tile[4]).pack())
            # notify player of all tiles that are already on the self.board
            for token in self.game.tokenMoves:
                connection.send(tiles.MessageMoveToken(
                    token[0], token[1], token[2], token[3]).pack())
            # notify the client of all players that have been eliminated from the current self.game
            for player in self.game.eliminatedPlayers:
                connection.send(tiles.MessagePlayerEliminated(player).pack())

            # if a self.game is running, notify the client of the real current turn
            connection.send(tiles.MessagePlayerTurn(
                self.game.activePlayers[self.game.currentTurnId]).pack())

    def timeout(self):
        """
        Called when a player takes too long to make a manual input move. 
        Makes a random (legitimate) move for them.
        """
        #msg in form [msg.idnum, msg.tileid, msg.rotation,msg.x, msg.y]
        print("TIMEOUT!")
        idnum = self.game.activePlayers[self.game.currentTurnId]

        if(not self.board.have_player_position(idnum)):  # if no token
            for tile in self.game.placedTiles:  # check to see whether tile has been placed
                if(tile[0] == idnum):
                    while(True):
                        if(self.board.set_player_start_position(idnum, tile[3], tile[4], random.randint(0, 7))):
                            self.update_tokens()
                            return
            while(True):  # if not tile has been placed
                msg = [idnum, self.connectedClients[idnum].currentTiles[random.randint(0, 3)], random.randint(0, 3), random.randrange(
                    0, tiles.BOARD_WIDTH), random.randrange(0, tiles.BOARD_HEIGHT)]

                if(self.board.set_tile(msg[3], msg[4], msg[1], msg[2], msg[0])):
                    self.place_tile(msg)
                    return

        if(self.board.have_player_position(idnum)):
            x, y, d = self.board.get_player_position(idnum)
            while(True):
                msg = [idnum, self.connectedClients[idnum].currentTiles[random.randint(
                    0, 3)], random.randint(0, 3), x, y]
                if(self.board.set_tile(msg[3], msg[4], msg[1], msg[2], msg[0])):
                    self.place_tile(msg)
                    return

    def make_move(self, buffer):
        """
        Called when a player makes a manual input move (adding a tile or chosing a token).
        Reads message from bytearray and checks its a legitimate move, if it is then self.board is updated.
        """
        while True:
            msg, consumed = tiles.read_message_from_bytearray(buffer)
            if not consumed:
                break
            buffer = buffer[consumed:]

            # sent by the player to put a tile onto the self.board (in all turns except
            # their second)
            if isinstance(msg, tiles.MessagePlaceTile):
                if(self.board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum)):
                    self.place_tile(
                        [msg.idnum, msg.tileid, msg.rotation, msg.x, msg.y])

            # sent by the player in the second turn, to choose their token's
            # starting path
            elif isinstance(msg, tiles.MessageMoveToken):
                if(not self.board.have_player_position(msg.idnum)):
                    if(self.board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position)):
                        self.update_tokens()

    def next_turn(self):
        """
        Called each time player whos turn it is finishes 'making' a move (through input, timeout or disconnection).
        Updates currentTurnID and restarts timer for the next player. If prevous self.game finished, chooses to start a new
        self.game (if connections >=2) or sets gameRunning to false.
        """
        self.game.timeoutTimer.cancel()
        self.game.timeoutTimer = threading.Timer(WAITTIME, self.timeout)

        # if enough players that self.game can continue; continue playing
        if(len(self.game.activePlayers) >= 2):
            # if at the end of the array next position is 0
            if(self.game.currentTurnId == len(self.game.activePlayers)-1):
                self.game.currentTurnId = 0
            else:
                self.game.currentTurnId += 1
            self.game.timeoutTimer.start()
            self.send_to_all(tiles.MessagePlayerTurn(
                self.game.activePlayers[self.game.currentTurnId]).pack())
            print("Move complete, next move by id:",
                  self.game.activePlayers[self.game.currentTurnId])
        # else if enough players to start a new self.game; start new self.game
        elif(len(self.send_to_all(None)) >= 2):
            self.new_game()

        else:  # if not enough players to start a new self.game
            print("Game Finished\n")
            self.board.reset()
            self.gameRunning = False

    def new_game(self):
        """
        Starts a new self.game for connected clients. Chooses randomly from the currently connected clients
        if number of clients > 4. Sets a random turn order for those chosen clients and gives each client
        a random selection of tiles. If self.game was prevously running, self.board and gamestate reset.
        """
        print("\nNew Game Started!")
        self.send_to_all(tiles.MessageCountdown().pack())
        time.sleep(SLEEPTIME)
        self.board.reset()
        self.gameRunning = True
        # chooses random idnums from all active connections
        sample = random.sample(self.send_to_all(None), min(
            len(self.send_to_all(None)), tiles.PLAYER_LIMIT))
        turn = random.randrange(0, len(sample))
        self.game = Gamestats(sample, turn)
        self.send_to_all(tiles.MessageGameStart().pack())

        for idnum in self.game.activePlayers:
            self.game.startingPlayers.append(idnum)
            self.send_to_all(tiles.MessagePlayerTurn(idnum).pack())

        print("Idnums in current game:", self.game.startingPlayers)

        for idnum in self.game.activePlayers:
            for index in range(tiles.HAND_SIZE):
                tileid = tiles.get_random_tileid()
                self.connectedClients[idnum].currentTiles[index] = tileid
                self.connectedClients[idnum].socketID.send(
                    tiles.MessageAddTileToHand(tileid).pack())

        self.next_turn()

    def accept_new_connection(self, sock):
        """
        Handles new connections as recieved by socket. Registers new client in both local server
        variables as well as selection register.
        """
        connection, addr = sock.accept()
        host, port = addr
        name = '{}:{}'.format(host, port)
        connection.setblocking(False)
        data = types.SimpleNamespace(addr=addr, inb=b'', outb=b'')
        events = selectors.EVENT_READ
        self.sel.register(connection, events, data=data)
        self.latestID += 1
        print('Received connection from client {}.'.format(self.latestID))
        connection.send(tiles.MessageWelcome(
            self.latestID).pack())  # welcome new player
        self.send_to_all(tiles.MessagePlayerJoined(
            name, self.latestID).pack())  # send everyone new player info
        # add new player to self.connectedClients
        self.connectedClients[self.latestID] = Socket(connection, name)
        self.update_player()

        if(not self.gameRunning and len(self.send_to_all(None)) >= 2):
            self.new_game()

    def accept_client_data(self, key, mask):
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
                self.sel.unregister(sock)
                sock.close()
                for idnum in range(len(self.connectedClients)):
                    if(sock == self.connectedClients[idnum].socketID):
                        print('Client {} disconnected.'.format(idnum))
                        self.connectedClients[idnum].active = False
                        if(self.gameRunning):
                            # if was a player in current self.game
                            if(idnum in self.game.activePlayers):
                                self.send_to_all(
                                    tiles.MessagePlayerEliminated(idnum).pack())
                                # was the disconnected players turn
                                if(self.game.activePlayers[self.game.currentTurnId] == idnum):
                                    self.game.timeoutTimer.cancel()
                                    self.game.currentTurnId -= 1
                                else:  # correct current run index if player removed was before it
                                    for index, playerID in enumerate(self.game.activePlayers):
                                        if(idnum == playerID and index < self.game.currentTurnId):
                                            self.game.currentTurnId -= 2
                                        elif(idnum == playerID):
                                            self.game.currentTurnId -= 1
                                self.game.activePlayers.remove(idnum)
                                self.next_turn()
                        self.send_to_all(tiles.MessagePlayerLeft(idnum).pack())# wasnt part of the game
                        return

                return

            buffer = bytearray()
            buffer.extend(chunk)
            if(sock == self.connectedClients[self.game.activePlayers[self.game.currentTurnId]].socketID and self.gameRunning):
                self.make_move(buffer)

    def start(self):
        # create a TCP/IP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # listen on all network interfaces
        sock.bind((self.host, self.port))
        print("Listening on {}.".format(sock.getsockname()))

        # have a maximum backlog of 5 clients
        sock.listen(5)
        sock.setblocking(False)

        # allow high level I/O multiplexing
        self.sel.register(sock, selectors.EVENT_READ, data=None)

        # infinite loop checking socket for incoming packages
        while True:
            events = self.sel.select(timeout=None)
            for key, mask in events:
                if key.data is None:
                    # if no data; must be a new client connection
                    self.accept_new_connection(key.fileobj)
                else:
                    # with data; exsiting client connection
                    self.accept_client_data(key, mask)


server = Server('localhost', 30020)
server.start()
