# CITS3002 2021 Assignment
#
# This file implements a basic server that allows a single client to play a
# single game with no other participants, and very little error checking.
#
# Any other clients that connect during this time will need to wait for the
# first client's game to complete.
#
# Your task will be to write a new server that adds all connected clients into
# a pool of players. When enough players are available (two or more), the server
# will create a game with a random sample of those players (no more than
# tiles.PLAYER_LIMIT players will be in any one game). Players will take turns
# in an order determined by the server, continuing until the game is finished
# (there are less than two players remaining). When the game is finished, if
# there are enough players available the server will start a new game with a
# new selection of clients.

import socket
import sys
import tiles
import selectors
import types 
import random
import time

class Gamestats:
  startingPlayers =[]
  currentPlayers = []
  eliminatedPlayers = []
  placedTiles = []
  tokenMoves = []
  currentTurnIndex = -1 #the index in for turnIndex that holds the idnum of the current turn






# create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# listen on all network interfaces
server_address = ('', 30020)
sock.bind(server_address)
print('listening on {}'.format(sock.getsockname()))

#have a maximum backlog of 5 clients
sock.listen(5)
sock.setblocking(False)

#allow high level I/O multiplexing
sel = selectors.DefaultSelector()
sel.register(sock, selectors.EVENT_READ, data=None)


#global variables

connectionID = [] #list of all connections in the form [id,socket]
board = tiles.Board() #current board state
latestID = -1 #last used ID when client joins
game = Gamestats()
gameRunning = False







def makemove(buffer):
  live_idnums = []
  for player in game.currentPlayers:
    live_idnums.append(player[0])

  global board
  connection = game.currentPlayers[game.currentTurnIndex][1]

  while True:
    msg, consumed = tiles.read_message_from_bytearray(buffer)
    if not consumed:
      break

    buffer = buffer[consumed:]

    print('Received message {}'.format(msg))

    # sent by the player to put a tile onto the board (in all turns except
    # their second)
    if isinstance(msg, tiles.MessagePlaceTile):
      if board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):

        sendallplayers(tiles.MessagePlaceTile(msg.idnum, msg.tileid, msg.rotation,msg.x, msg.y).pack())
        game.placedTiles.append([msg.idnum, msg.tileid, msg.rotation,msg.x, msg.y])
        # notify client that placement was successful
        connection.send(msg.pack())

        # check for token movement
        positionupdates, eliminated = board.do_player_movement(live_idnums)

        for msg in positionupdates:
          game.tokenMoves.append([msg.idnum,msg.x,msg.y,msg.position])
          sendallplayers(tiles.MessageMoveToken(msg.idnum,msg.x,msg.y,msg.position).pack())
  
        # pickup a new tile
        tileid = tiles.get_random_tileid()
        connection.send(tiles.MessageAddTileToHand(tileid).pack())
        connection.send(tiles.MessageAddTileToHand(tileid).pack())
  
        for index,player in enumerate(game.currentPlayers):
          if player[0] in eliminated:
            sendallplayers(tiles.MessagePlayerEliminated(player[0]).pack())
            game.currentPlayers.remove(player)
            game.eliminatedPlayers.append(player[0])
            if(index <= game.currentTurnIndex):
              game.currentTurnIndex -= 1
        nextturn()
        
        
    # sent by the player in the second turn, to choose their token's
    # starting path
    elif isinstance(msg, tiles.MessageMoveToken):
      if not board.have_player_position(msg.idnum):
        if board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):
          # check for token movement

          positionupdates, eliminated = board.do_player_movement(live_idnums)

          for msg in positionupdates:
            sendallplayers(tiles.MessageMoveToken(msg.idnum,msg.x,msg.y,msg.position).pack())
          
          for index,player in enumerate(game.currentPlayers):
            if player[0] in eliminated:
              sendallplayers(tiles.MessagePlayerEliminated(player[0]).pack())
              game.currentPlayers.remove(player)
              game.eliminatedPlayers.append(player[0])
              if(index <= game.currentTurnIndex):
                game.currentTurnIndex -= 1

          nextturn()



def systemPause():
    time.sleep(3)


def nextturn():
  global game
  global gameRunning

  if(len(game.currentPlayers) >= 2): #if enough players that game can continue; continue playing
    if(game.currentTurnIndex == len(game.currentPlayers)-1):
      game.currentTurnIndex=0
    else: 
      game.currentTurnIndex +=1 
    sendallplayers(tiles.MessagePlayerTurn(game.currentPlayers[game.currentTurnIndex][0]).pack())
  
  elif(len(connectionID)>= 2):       #if enough players to start a new game; start new game
    print("should get here?")
    newgame()

  else: gameRunning = False          #else, stop game



def sendallplayers(update):
  for player in connectionID:
    player[1].send(update)



def service_connection(key, mask):
  sock = key.fileobj
  data = key.data
  if mask & selectors.EVENT_READ:
      chunk = sock.recv(4096)  # Should be ready to read
      if not chunk:
        sel.unregister(sock)
        sock.close() #todo?

        for index,con in enumerate(connectionID):
          if(sock == con[1]):
            idnum = con[0]
            connectionID.remove(con)
            if(gameRunning and con[0] in game.startingPlayers and con[0] not in game.eliminatedPlayers): 
                game.eliminatedPlayers.append(con[0])
                game.currentPlayers.remove(con)
                sendallplayers(tiles.MessagePlayerEliminated(idnum).pack())
                if(index == game.currentTurnIndex):
                  game.currentTurnIndex -= 1
                elif(index <game.currentTurnIndex):
                  game.currentTurnIndex -= 1
                nextturn()
            else: #wasnt part of the game
              sendallplayers(tiles.MessagePlayerLeft(idnum).pack())
            

        print('client {} disconnected'.format(data.addr))
        return
      
      buffer = bytearray()
      buffer.extend(chunk)
      if(sock == game.currentPlayers[game.currentTurnIndex][1] and gameRunning):
        makemove(buffer)



def accept_wrapper(sock):
  global latestID
  connection, addr = sock.accept() 
  print('received connection from {}'.format(addr))

  connection.setblocking(False)
  data = types.SimpleNamespace(addr=addr, inb=b'', outb=b'')
  events = selectors.EVENT_READ
  sel.register(connection, events, data=data)

  host, port = addr
  name = '{}:{}'.format(host, port)
  
  latestID += 1

  #send all previous player names to current player
  for con in connectionID:
    connection.send(tiles.MessagePlayerJoined(con[2], con[0]).pack())
  
  connectionID.append([latestID,connection,name])
  connection.send(tiles.MessageWelcome(latestID).pack())

  #send current player name to all previous players
  for con in connectionID:
    con[1].send(tiles.MessagePlayerJoined(name, latestID).pack())

  if(gameRunning):
    updateplayer(len(connectionID)-1)
    if(len(game.currentPlayers)<= 1):
      newgame()
  elif(len(connectionID)>=2):
    newgame()





def updateplayer(connectID):
  connection = connectionID[connectID][1]
  for player in game.startingPlayers: #Notify the client of the id number of all players that started in the current game
    connection.send(tiles.MessagePlayerTurn(player).pack())
  for tile in game.placedTiles: #Notify the client of all token positions, for players that have a token position
    connection.send(tiles.MessagePlaceTile(tile[0],tile[1],tile[2],tile[3],tile[4]).pack())
  for token in game.tokenMoves: #Notify the client of all tiles that are already on the board
    connection.send(tiles.MessageMoveToken(token[0],token[1],token[2],token[3]).pack())
  for player in game.eliminatedPlayers: #Notify the client of all players that have been eliminated from the current game
    connection.send(tiles.MessagePlayerEliminated(player).pack())
  connection.send(tiles.MessagePlayerTurn(game.currentPlayers[game.currentTurnIndex][0]).pack()) #Notify the client of the real current turn




    
  


def newgame():
  global game
  global gameRunning
  systemPause()
  board.reset()
  game = Gamestats()
  gameRunning = True
  game.currentPlayers = random.sample(connectionID, min(len(connectionID),tiles.PLAYER_LIMIT))
  game.currentTurnIndex = random.randrange(0,len(game.currentPlayers))

  for player in game.currentPlayers:
    player[1].send(tiles.MessageGameStart().pack())
    game.startingPlayers.append(player[0])
    for _ in range(tiles.HAND_SIZE):
      tileid = tiles.get_random_tileid()
      player[1].send(tiles.MessageAddTileToHand(tileid).pack())

  for player in game.currentPlayers: #Notify the players of the id number of all other players 
    for idnum in game.startingPlayers:
      player[1].send(tiles.MessagePlayerTurn(idnum).pack())
  nextturn()





#infinite loop checking socket for incomming packages 
while True:
    events = sel.select(timeout=None)
    for key, mask in events:
        if key.data is None:
          #if no data; must be a new client connection
          accept_wrapper(key.fileobj)
        else:
          #with data; exsiting client connection
          service_connection(key, mask)
  

