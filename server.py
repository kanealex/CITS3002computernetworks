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
import threading
import sys
import tiles
import selectors
import types 
import random
import time
import copy
 

WAITTIME = 1

class Gamestats:
  startingPlayers =[] #can remove
  currentPlayers = []
  eliminatedPlayers = []
  placedTiles = []
  tokenMoves = []
  timeoutTimer = threading.Timer(WAITTIME,None)
  currentTurnIndex = -1 #the index in for turnIndex that holds the idnum of the current turn
  def reset(self):
    self.startingPlayers.clear() #can remove
    self.currentPlayers.clear()
    self.eliminatedPlayers.clear()
    self.placedTiles.clear()
    self.tokenMoves.clear()
    self.timeoutTimer = threading.Timer(10,None)
    self.currentTurnIndex = -1 
    

#global variables

connectionID = [] #list of all connections in the form [id,socket]
board = tiles.Board() #current board state
latestID = -1 #last used ID when client joins
game = Gamestats()
gameRunning = False



# create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# listen on all network interfaces
server_address = ('', 30020)
sock.bind(server_address)
print("Listening on {}.".format(sock.getsockname()))

#have a maximum backlog of 5 clients
sock.listen(5)
sock.setblocking(False)

#allow high level I/O multiplexing
sel = selectors.DefaultSelector()
sel.register(sock, selectors.EVENT_READ, data=None)



def makemove(buffer):
  connection = game.currentPlayers[game.currentTurnIndex][1]
  live_idnums = []
  for player in game.currentPlayers:
    live_idnums.append(player[0])

  while True:
    msg, consumed = tiles.read_message_from_bytearray(buffer)
    if not consumed:
      break

    buffer = buffer[consumed:]

    # sent by the player to put a tile onto the board (in all turns except
    # their second)
    if isinstance(msg, tiles.MessagePlaceTile):
      if(board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum)):
        placetile([msg.idnum, msg.tileid, msg.rotation,msg.x, msg.y],connection,live_idnums)
  

    # sent by the player in the second turn, to choose their token's
    # starting path
    elif isinstance(msg, tiles.MessageMoveToken):
      if( not board.have_player_position(msg.idnum)):
        if(board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position)):
          updatetokens(connection,live_idnums)


#msg in form [msg.idnum, msg.tileid, msg.rotation,msg.x, msg.y]
def placetile(msg,connection,live_idnums):
    
    #print("Move made by Player: ",msg[0]," placed tileID",msg[1])
    #print("Player ",game.currentTurnIndex,"wants to play: ",msg[1],"from tiles: ",game.currentPlayers[msg[0]][3])

    game.timeoutTimer.cancel()
    sendallplayers(tiles.MessagePlaceTile(msg[0],msg[1], msg[2],msg[3], msg[4]).pack())
    game.placedTiles.append([msg[0],msg[1], msg[2],msg[3], msg[4]])
    # notify client that placement was successful

    # pickup a new tile
    tileid = tiles.get_random_tileid()
    connection.send(tiles.MessageAddTileToHand(tileid).pack())
    updatetokens(connection, live_idnums)

    for index,player in enumerate(game.currentPlayers):
      if(player[3][index] == msg[1]):
        player[3][index] = tileid


#msg in form [msg.idnum, msg.tileid, msg.rotation,msg.x, msg.y]
def updatetokens(connection,live_idnums):
    game.timeoutTimer.cancel()
  
    # check for token movement
    positionupdates, eliminated = board.do_player_movement(live_idnums)

    for msg in positionupdates:
      game.tokenMoves.append([msg.idnum,msg.x,msg.y,msg.position])
      sendallplayers(tiles.MessageMoveToken(msg.idnum,msg.x,msg.y,msg.position).pack())
    
    for index,player in enumerate(game.currentPlayers):
      if player[0] in eliminated:
        sendallplayers(tiles.MessagePlayerEliminated(player[0]).pack())
        game.currentPlayers.remove(player)
        game.eliminatedPlayers.append(player[0])
        if(index <= game.currentTurnIndex):
          game.currentTurnIndex -= 1
    nextturn()




def timeout():
  game.timeoutTimer.cancel()
  connection = game.currentPlayers[game.currentTurnIndex][1]
  live_idnums = []
  for player in game.currentPlayers:
    live_idnums.append(player[0])
  idnum = game.currentPlayers[game.currentTurnIndex][0]
  #print("Player: ",idnum," timed out. Random turn made.")
  
  if(not board.have_player_position(idnum)): #if no token
      for tile in game.placedTiles: #check to see whether tile has been placed 
        if(tile[0] == idnum):
          while(True):
            if(board.set_player_start_position(idnum,tile[3], tile[4], random.randint(0,7))):
              updatetokens(connection,live_idnums)
              return
      while(True): #if not tile has been placed
        msg = [idnum,0,random.randint(0,3),random.randrange(0,tiles.BOARD_WIDTH),random.randrange(0,tiles.BOARD_HEIGHT)]
        a=random.randint(0,3)
        msg[1] = game.currentPlayers[msg[0]][3][a]
        print(game.currentPlayers[msg[0]][3])
        print("\n",a)
        if(board.set_tile(msg[3],msg[4], msg[1], msg[2], msg[0])):
          placetile(msg, connection, live_idnums)
          return

  if(board.have_player_position(idnum)):
    x,y,d = board.get_player_position(idnum)  
    while(True):
      msg = [idnum,0,random.randint(0,3),x,y]
      a = random.randint(0,3)
      msg[1] = game.currentPlayers[msg[0]][3][a]
      print(game.currentPlayers[msg[0]][3])
      print("\n",a)
      if(board.set_tile(msg[3],msg[4], msg[1], msg[2], msg[0])):
        placetile(msg, connection, live_idnums)
        return


def nextturn():
  global game
  global gameRunning
  game.timeoutTimer.cancel()
  game.timeoutTimer = threading.Timer(WAITTIME,timeout)
  game.timeoutTimer.start()

  if(len(game.currentPlayers) >= 2): #if enough players that game can continue; continue playing
    if(game.currentTurnIndex == len(game.currentPlayers)-1):
      game.currentTurnIndex=0
    else: 
      game.currentTurnIndex +=1 
    sendallplayers(tiles.MessagePlayerTurn(game.currentPlayers[game.currentTurnIndex][0]).pack())
  
  elif(len(connectionID)>= 2):       #if enough players to start a new game; start new game
    newgame()

  else:
    print("\nGame Finished")
    game.timeoutTimer.cancel()
    board.reset()
    gameRunning = False          #else, stop game



def sendallplayers(update):
  for player in connectionID:
    player[1].send(update)



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
  time.sleep(1)
  board.reset()
  game.reset()
  gameRunning = True
  game.currentPlayers = random.sample(connectionID, min(len(connectionID),tiles.PLAYER_LIMIT)).copy()
  game.currentTurnIndex = random.randrange(0,len(game.currentPlayers))
  print("\nNew Game Starting! ",len(game.currentPlayers)," players.\n")

  for player in game.currentPlayers:
    player[1].send(tiles.MessageGameStart().pack())
    game.startingPlayers.append(player[0])
    for index in range(tiles.HAND_SIZE):
      tileid = tiles.get_random_tileid()
      player[3][index] = tileid
      player[1].send(tiles.MessageAddTileToHand(tileid).pack())
  
  for player in game.currentPlayers: #Notify the players of the id number of all other players  
    for idnum in game.startingPlayers:
      player[1].send(tiles.MessagePlayerTurn(idnum).pack())

  nextturn()












def accept_client_data(key, mask):
  sock = key.fileobj
  data = key.data
  if mask & selectors.EVENT_READ:
      chunk = sock.recv(4096)  # Should be ready to read
      if not chunk:
        sel.unregister(sock)
        sock.close() #todo?

        for index,con in enumerate(connectionID):
          if(sock == con[1]):
            print('Client {} disconnected.'.format(con[0]))
            idnum = con[0]
            connectionID.remove(con)
            if(gameRunning and con[0] in game.startingPlayers and con[0] not in game.eliminatedPlayers): 
                game.eliminatedPlayers.append(con[0])
                game.currentPlayers.remove(con)
                sendallplayers(tiles.MessagePlayerEliminated(idnum).pack())
                if(index == game.currentTurnIndex):
                  game.timeoutTimer.cancel()
                  game.currentTurnIndex -= 1
                  nextturn()
                elif(index <game.currentTurnIndex):
                  game.currentTurnIndex -= 1
            else: #wasnt part of the game
              sendallplayers(tiles.MessagePlayerLeft(idnum).pack())
          
        return
      
      buffer = bytearray()
      buffer.extend(chunk)
      if(sock == game.currentPlayers[game.currentTurnIndex][1] and gameRunning):
        makemove(buffer)



def accept_new_connection(sock):
  global latestID
  connection, addr = sock.accept() 

  connection.setblocking(False)
  data = types.SimpleNamespace(addr=addr, inb=b'', outb=b'')
  events = selectors.EVENT_READ
  sel.register(connection, events, data=data)

  host, port = addr
  name = '{}:{}'.format(host, port)
  
  latestID += 1

  print('Received connection from client {}.'.format(latestID))

  #send all previous player names to current player
  for con in connectionID:
    connection.send(tiles.MessagePlayerJoined(con[2], con[0]).pack())
  
  connectionID.append([latestID,connection,name,[None,None,None,None]])
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





#infinite loop checking socket for incomming packages 
while True:
    events = sel.select(timeout=None)
    for key, mask in events:
        if key.data is None:
          #if no data; must be a new client connection
          accept_new_connection(key.fileobj)
        else:
          #with data; exsiting client connection
          accept_client_data(key, mask)
    
  

