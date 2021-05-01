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
from enum import Enum
import socket
import sys
import tiles


class ClientType(Enum):
  DISCONNECTED = 0
  GAME = 1
  QUEUE = 2
  


class client:
  def __init__(self, connection,address,ClientType,idnum,buffer): 
        self.connection = connection 
        self.address = address
        self.ClientType = ClientType
        self.idnum = idnum
        self.buffer = buffer
activeClients = []
turnID = 0






def startgame1(players):
  idnum = 0

  # set up all players with welcomes and add random card to their hands.
  for individual in players:
    host, port = individual.address
    name = '{}:{}'.format(host, port)
    individual.connection.send(tiles.MessageWelcome(idnum).pack())
    individual.connection.send(tiles.MessagePlayerJoined(name, idnum).pack())
    individual.connection.send(tiles.MessageGameStart().pack())
    for _ in range(tiles.HAND_SIZE):
      tileid = tiles.get_random_tileid()
      individual.connection.send(tiles.MessageAddTileToHand(tileid).pack())
    idnum += 1


  while True:
    for individual in players:
      chunk = connection.recv(4096)
      if not chunk:
        print('client {} disconnected'.format(individual.address))
        return
        
  print("ok")



  



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
      # star  ting path
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





def newplayer(connection, client_address):
  newclient = client(connection, client_address,ClientType.GAME,len(activeClients),bytearray())
  activeClients.append(newclient)
  connection.send(tiles.MessageWelcome(newclient.idnum).pack())
  print("added new player")
  

def initgame():
  for client in activeClients:
    host, port = client.address
    name = '{}:{}'.format(host, port)
    connection.send(tiles.MessagePlayerJoined(name, client.idnum).pack())
    connection.send(tiles.MessageGameStart().pack())

    for _ in range(tiles.HAND_SIZE):
      tileid = tiles.get_random_tileid()
      client.connection.send(tiles.MessageAddTileToHand(tileid).pack())

def clientconnections(activeClients):
  print("here!~")
  for clients in activeClients:
    chunk = clients.connection.recv(4096)
    print(chunk)
    if not chunk:
      print('client {} disconnected'.format(clients.address))
      return

def turn():
  idnum = turnID
  live_idnums = [0,1]
  for client in activeClients:
    client.connection.send(tiles.MessagePlayerTurn(idnum).pack())
  board = tiles.Board()
  buffer = bytearray()

  chunk = activeClients[turnID].connection.recv(4096)
  if not chunk:
    print('client {} disconnected'.format(activeClients[turnID].address))
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
          activeClients[turnID].connection.send(msg.pack())

          # check for token movement
          positionupdates, eliminated = board.do_player_movement(live_idnums)

          for msg in positionupdates:
            for client in activeClients:
              client.connection.send(msg.pack())
          
          if idnum in eliminated:
            connection.send(tiles.MessagePlayerEliminated(idnum).pack())
            return

          # pickup a new tile
          tileid = tiles.get_random_tileid()
          activeClients[turnID].connection.send(tiles.MessageAddTileToHand(tileid).pack())

          # start next turn
          return

      # sent by the player in the second turn, to choose their token's
      # star  ting path
      elif isinstance(msg, tiles.MessageMoveToken):
        print('second tjurn0')
        if not board.have_player_position(msg.idnum):
          if board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):
            # check for token movement
            positionupdates, eliminated = board.do_player_movement(live_idnums)

            for msg in positionupdates:
              for client in activeClients:
                client.connection.send(msg.pack())
            
            if idnum in eliminated:
              for client in activeClients:
                client.connection.send(tiles.MessagePlayerEliminated(idnum).pack())
                return
            # start next turn
        return

  

    
            

# create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# listen on all network interfaces
server_address = ('', 30020)
sock.bind(server_address)
print('listening on {}'.format(sock.getsockname()))
sock.listen(5)


temp = 0
while True:
  #handle each new connection independently
  #add new clients
  print('top loop')
  if(temp == 0 or temp == 1):
    connection, client_address = sock.accept()
    print('received connection from {}'.format(client_address))
    newplayer(connection, client_address)
  print('kepsgoing')
  temp += 1
 
  if(len(activeClients)>=2 and temp == 2):
    
    print("gamestarted!")
    initgame()

  print('kepsgoings11')
  if(temp >= 2):
    print('newturn')
    turn()


  

  #IF CLIENTS DISCONNECT
  #clientconnections(activeClients)
  
      
  







  #if(len(activeClients)>1):
  #  print('Number of active clients: {0} \nStarting Game!'.format(len(activeClients)))
  #  startgame(activeClients)
  
  #client_handler(connection, client_address)
