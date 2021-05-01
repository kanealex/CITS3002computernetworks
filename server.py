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

sel = selectors.DefaultSelector()


def client_handler(connection, address):
  host, port = address
  name = '{}:{}'.format(host, port)

  idnum = 0
  live_idnums = [idnum]

  connection.send(tiles.MessageWelcome(idnum).pack())
  connection.send(tiles.MessagePlayerJoined(name, idnum).pack())
  connection.send(tiles.MessageGameStart().pack())

  for _ in range(tiles.HAND_SIZE):
    tileid = tiles.get_random_tileid()
    connection.send(tiles.MessageAddTileToHand(tileid).pack())
  
  connection.send(tiles.MessagePlayerTurn(idnum).pack())
  
  board = tiles.Board()

  buffer = bytearray()

  while True:
    chunk = connection.recv(4096)
    if not chunk:
      print('client {} disconnected'.format(address))
      return

    buffer.extend(chunk)

    while True:
      msg, consumed = tiles.read_message_from_bytearray(buffer)
      if not consumed:
        break

      buffer = buffer[consumed:]

      print('received message {}'.format(msg))

      # sent by the player to put a tile onto the board (in all turns except
      # their second)
      if isinstance(msg, tiles.MessagePlaceTile):
        if board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):
          # notify client that placement was successful

          connection.send(msg.pack())

          # check for token movement
          positionupdates, eliminated = board.do_player_movement(live_idnums)

          for msg in positionupdates:
            connection.send(msg.pack())
          
          if idnum in eliminated:
            connection.send(tiles.MessagePlayerEliminated(idnum).pack())
            return

          # pickup a new tile
          tileid = tiles.get_random_tileid()
          connection.send(tiles.MessageAddTileToHand(tileid).pack())

          # start next turn
          connection.send(tiles.MessagePlayerTurn(idnum).pack())

      # sent by the player in the second turn, to choose their token's
      # starting path
      elif isinstance(msg, tiles.MessageMoveToken):
        if not board.have_player_position(msg.idnum):
          if board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):
            # check for token movement
            positionupdates, eliminated = board.do_player_movement(live_idnums)

            for msg in positionupdates:
              connection.send(msg.pack())
            
            if idnum in eliminated:
              connection.send(tiles.MessagePlayerEliminated(idnum).pack())
              return
            
            # start next turn
            connection.send(tiles.MessagePlayerTurn(idnum).pack())


# create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# listen on all network interfaces
server_address = ('', 30020)
sock.bind(server_address)

print('listening on {}'.format(sock.getsockname()))

sock.listen(5)
#5 is the backlog parameter
sock.setblocking(False)
sel.register(sock, selectors.EVENT_READ, data=None)




def makemove(buffer):
  live_idnums = []
  live_idnums.append(0)
  live_idnums.append(1)
  global board
  connection = playerID[currentTurnIndex][1]

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

        for con in playerID:
          con[1].send(tiles.MessagePlaceTile(msg.idnum, msg.tileid, msg.rotation,msg.x, msg.y).pack())
        # notify client that placement was successful
        connection.send(msg.pack())

        # check for token movement
        positionupdates, eliminated = board.do_player_movement(live_idnums)

        
        for con in playerID:
          for msg in positionupdates:
            con[1].send(msg.pack())
        
        if playerID[currentTurnIndex][0] in eliminated:
          print("SHOULDNT GET HERE")
          connection.send(tiles.MessagePlayerEliminated(idnum).pack())
          return 
        print("did it?")
        # pickup a new tile
        tileid = tiles.get_random_tileid()
        connection.send(tiles.MessageAddTileToHand(tileid).pack())
        nextturn()
        
        
    # sent by the player in the second turn, to choose their token's
    # starting path
    elif isinstance(msg, tiles.MessageMoveToken):
      if not board.have_player_position(msg.idnum):
        if board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):
          # check for token movement

          positionupdates, eliminated = board.do_player_movement([0,1]) #CAHDNASDNSANDSANDNASDNASDNDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD

          for con in playerID:
            for msg in positionupdates:
              con[1].send(msg.pack())
          
          if playerID[currentTurnIndex][0] in eliminated:
            print("SHOULDNT GET HERE")
            connection.send(tiles.MessagePlayerEliminated(idnum).pack())
            return
          nextturn()
  
def nextturn():
  global currentTurnIndex
  if(currentTurnIndex == 0):#dumb af
    currentTurnIndex=1
  else: 
    currentTurnIndex=0
  print(currentTurnIndex)

  for con in playerID:
    con[1].send(tiles.MessagePlayerTurn(playerID[currentTurnIndex][0]).pack())
          

  



def service_connection(key, mask):
  global currentTurnIndex
  sock = key.fileobj
  data = key.data
  if mask & selectors.EVENT_READ:
      chunk = sock.recv(4096)  # Should be ready to read
      if not chunk:
        sel.unregister(sock)
        sock.close() #todo?
        print('client {} disconnected'.format(data.addr))
        return
      
      buffer = bytearray()
      buffer.extend(chunk)
      if(sock == playerID[currentTurnIndex][1]):
          makemove(buffer)
      else: 
        return

  if mask & selectors.EVENT_WRITE:
      if data.outb:
          print('echoing', repr(data.outb), 'to', data.addr)
          sent = sock.send(data.outb)  # Should be ready to write
          data.outb = data.outb[sent:]





def accept_wrapper(sock):
  connection, addr = sock.accept() 
  print('received connection from {}'.format(addr))
  connection.setblocking(False)

  data = types.SimpleNamespace(addr=addr, inb=b'', outb=b'')
  events = selectors.EVENT_READ
  sel.register(connection, events, data=data)

  host, port = addr
  name = '{}:{}'.format(host, port)
  
  idnum = len(connectionID)

  #send all previous player names to current player
  for con in connectionID:
    connection.send(tiles.MessagePlayerJoined(con[2], con[0]).pack())
  
  connectionID.append([idnum,connection,name])
  connection.send(tiles.MessageWelcome(idnum).pack())

#send current player name to all previous players
  for con in connectionID:
    con[1].send(tiles.MessagePlayerJoined(name, idnum).pack())


  if(len(connectionID)>1):
    startgame()


      

def startgame():
  #TODO select players first
  for con in connectionID:
    playerID.append([con[0],con[1]])

  global currentTurnIndex
  currentTurnIndex = random.randrange(0,len(playerID))
  
  for con in playerID:
    con[1].send(tiles.MessageGameStart().pack())
    for _ in range(tiles.HAND_SIZE):
      tileid = tiles.get_random_tileid()
      con[1].send(tiles.MessageAddTileToHand(tileid).pack())
  nextturn()
  




playerID = [] #list of current players in the form [id,socket]
connectionID = [] #list of all connections in the form [id,socket]
currentTurnIndex = 0 #the index in the array playerID of the current turn
board = tiles.Board()

while True:
    events = sel.select(timeout=None)
    for key, mask in events:
        if key.data is None:
            accept_wrapper(key.fileobj)
        else:
            service_connection(key, mask)
  

