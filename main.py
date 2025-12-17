import socketio
from werkzeug.serving import run_simple
from typing import List, Dict, Literal, TypedDict
from random import shuffle
from threading import Thread
import time
import uuid
from functools import wraps

sio = socketio.Server(cors_allowed_origins=[
  "http://localhost:3000",
  "https://joudialiya.pythonanywhere.com"
  ], async_mode='threading')
app = socketio.WSGIApp(sio)

class PlayerHand(TypedDict):
  user: str
  hand: List[str]

class Room(TypedDict):
  state: Literal["PAUSE", "DEAL", "TURN", "END", "TERMINATE"]
  turn_state: Literal["DRAW", "SHED", "SHOW"]
  thread: Thread
  stock: List[str]
  table: List[str]
  players: List[PlayerHand]
  turn: int
  leader: str
  winner_hand: List[List[str]]
  drawn_card: None
  drawn_from: Literal["TABLE", "STOCK"] 

class Player(TypedDict):
  user: str
  sio: str

SYMBOLS = ["♠", "♥", "♦", "♣"]
CARDS = (
  [chr(n) for n in range(0x1F0A1, 0x1F0AF)] +
  [chr(n) for n in range(0x1F0B1, 0x1F0BF)] +
  [chr(n) for n in range(0x1F0C1, 0x1F0CF)] +
  [chr(n) for n in range(0x1F0D1, 0x1F0DF)]
)

CARDS.remove(chr(0x1F0AC))
CARDS.remove(chr(0x1F0BC))
CARDS.remove(chr(0x1F0CC))
CARDS.remove(chr(0x1F0DC))

def decode_card(card: str) -> Dict:
  card = ord(card)
  number = card & 0x0000F
  card_type = ((card & 0x000F0) >> 4) - 0xA
  return {
    "number": number,
    "symbol": SYMBOLS[card_type]
  }

ROOMS: Dict[str, Room] = {
}
USER_SID: Dict[str, str] = {
}
SID_USER: Dict[str, str] = {
}
INIT_HAND_COUNT = 12

def structured_room_state(room_id):
  room = ROOMS.get(room_id)
  
  state = room.copy()
  state["players"] = [player["user"] for player in state["players"]]
  del state["thread"]
  
  return {
    "state": state,
    "room_id": room_id 
  }

def party_thread(room_id: str):
  is_finished = False
  room = ROOMS[room_id]
  while not is_finished:
    ##################################################################
    sio.emit('room_state', structured_room_state(room_id), room=[USER_SID.get(p["user"]) for p in room["players"]])
    ##################################################################
    if room["state"] == "PAUSE":
      pass
    elif room["state"] == "DEAL":
      for i in range(0, INIT_HAND_COUNT):
        for player in room["players"]:
          card = room["stock"].pop()
          player["hand"].append(card)
          sio.emit(
            "hand",
            {"hand": player["hand"], "room_id": room_id},
            room=USER_SID.get(player["user"]))
          print("Draw", card, USER_SID.get(player["user"]))
          time.sleep(1) 
      room["state"] = "TURN"
      room["turn_state"] = "DRAW"
    elif room["state"] == "TURN":
      player_index = room["turn"]
      player = room["players"][player_index]
      sio.emit(
        "info",
        {"msg": f"It is your turn play ! {room.get('turn_state')} ({room_id})", "room_id": room_id},
        room=USER_SID.get(player["user"]))
      sio.emit(
        "info",
        {"msg": f"It is ({player.get('user')}) turn play! ({room.get('state')})", "room_id": room_id},
        room=[USER_SID.get(p[ "user"]) for p in room["players"]],
        skip_sid=USER_SID.get(player["user"]))
    elif room["state"] == "END":
      sio.emit(
        "info",
        {"msg": f"The game ended (Winner: {player.get('user')}) ({room_id})", "room_id": room_id},
        room=[USER_SID.get(p["user"]) for p in room["players"]])
      sio.emit(
        "winner_hand",
        {"hand": room["winner_hand"], "room_id": room_id},
        room=[USER_SID.get(p["user"]) for p in room["players"]])
      is_finished = True
    elif room["state"] == "TERMINATE":
      is_finished = True
    time.sleep(1)

def init_room(name: str):
  if ROOMS.get(name):
    raise Exception("Room exists !")
  cards = CARDS.copy()
  shuffle(cards)
  ROOMS[name] = {
    "thread": Thread(target=party_thread, args=[name], daemon=True),
    "turn": 0,
    "stock": cards,
    "players": [],
    "table": [],
    "state": "PAUSE",
    "winner_hand": None,
    "drawn_card": None,
    "drawn_from": "STOCK"
  }

#########################################
# Decorators                            #
#########################################
def require_room(func):

  @wraps(func)
  def wrapper(sid, data, *args, **kwargs):
    room_id = data.get("room_id")
    room = ROOMS.get(room_id)
    print(f"{sid} attempts to join {room_id}")

    if not room:
      sio.emit("info", f"Room {room_id} does not exist", room=sid)
      return
    
    kwargs["room_id"] = room_id
    kwargs["room"] = room
    print("===> require room:", kwargs)
    func(sid, data, *args, **kwargs)
  return wrapper

def require_joined(joined=True):
  def outer(func):
    @wraps(func)
    def wrapper(sid, data, *args, **kwargs):
      print(func, kwargs)
      room_id = kwargs["room_id"]
      room = kwargs["room"]

      if joined and SID_USER.get(sid) not in map(lambda player: player["user"], room["players"]):
        sio.emit("info", { "msg": f"Your are not joined {room_id}" }, room=sid)
        return
      if not joined and SID_USER.get(sid) in map(lambda player: player["user"], room["players"]):
        sio.emit("info", { "msg": f"Your are already in {room_id}" }, room=sid)
        return
      func(sid, data, *args, **kwargs)
    return wrapper
  return outer

def require_turn(func):
  @wraps(func)
  def wrapper(sid, data, *args, **kwargs):

    room_id = kwargs["room_id"]
    room = kwargs["room"]
    
    player_turn = room["players"][room["turn"]]
    
    if USER_SID.get(player_turn["user"]) != sid:
      sio.emit('info', {'msg': f'It is not your turn to play'}, room=sid)
      return
    func(sid, data, *args, **kwargs)
  return wrapper

def require_leader(func):
  @wraps(func)
  def wrapper(sid, data, *args, **kwargs):

    room_id = kwargs["room_id"]
    room = kwargs["room"]
    if USER_SID.get(room["leader"]) != sid:
      sio.emit('info', {'msg': f'You are not the leader.'}, room=sid)
      return
    func(sid, data, *args, **kwargs)
  return wrapper

@sio.event
def connect(sid, environ, auth: Dict):
  print(f"{sid} {auth} connected")
  user = auth.get("user")
  if not user:
    sio.emit('info', {'msg': f'No user provided'}, room=sid)
    sio.disconnect(sid)
  else:
    if USER_SID.get(user):
      sio.emit('info', {'msg': f'User {user} already connected ({sid})'}, room=sid)
    
    USER_SID[user] = sid
    SID_USER[sid] = user 
    sio.emit('info', {'msg': f'User {user} has connected ({sid})'}, room=sid)

@sio.event
def disconnect(sid):
  print(f"{sid} disconnected")
  user = SID_USER.get(sid)
  del USER_SID[user]
  del SID_USER[sid]

@sio.event
def create_room(sid):
  room_id = str(uuid.uuid4())
  
  init_room(room_id)
  room = ROOMS[room_id]
  room["players"].append({
    "user": SID_USER.get(sid),
    "hand": []
  })
  room["leader"] = SID_USER.get(sid)
  
  sio.emit('info', {'msg': f'New room created ({room_id})'}, room=list(SID_USER.keys()))
  sio.emit("rooms", { "rooms":  [structured_room_state(room_id) for room_id in ROOMS.keys()] }, room=list(SID_USER.keys()))

@sio.event
def rooms(sid):
  sio.emit("rooms", { "rooms" : [structured_room_state(room_id) for room_id in ROOMS.keys()] }, room=sid)

@sio.event
@require_room
def room_state(sid, data, **kwargs):
  room_id = kwargs["room_id"]
  room = kwargs["room"]
  sio.emit('room_state', structured_room_state(room_id), room=sid)

@sio.event
@require_room
@require_joined(joined=False)

def join(sid, data, **kwargs):
  room_id = kwargs["room_id"]
  room = kwargs["room"]
  
  print(f"{sid} attempts to join {room_id}")

  if room["thread"].is_alive():
    sio.emit("info", {"msg": f"Party already started"}, room=sid)
  else:
    room["players"].append({
      "user": SID_USER.get(sid),
      "hand": []
    })
    sio.emit(
      "info",
      {"msg": f"{SID_USER.get(sid)} joined {room_id}"},
      room=[USER_SID.get(player["user"]) for player in room["players"]]) 
    ##################################################################
    sio.emit('room_state', structured_room_state(room_id), room=[USER_SID.get(p["user"]) for p in room["players"]])
    ##################################################################

@sio.event
@require_room
@require_joined()

def kill_room(sid, data, **kwargs):
  room_id = kwargs["room_id"]
  room = kwargs["room"]
  
  print(f"{sid} attempts to join {room_id}")
  if room["thread"].is_alive():
    sio.emit("info", {"msg": f"Party already started"}, room=sid)
  room["state"] = "TERMINATE"

@sio.event
@require_room
@require_joined()
def hand(sid, data, **kwargs):
  room_id = kwargs["room_id"]
  room = kwargs["room"]

  player = None
  for entry in room["players"]:
    if entry["user"] == SID_USER.get(sid):
      player = entry
      break
  sio.emit("hand", { "hand": player["hand"], "room_id": room_id }, room=sid)

@sio.event
@require_room
@require_joined()

def table(sid, data, **kwargs):
  room_id = kwargs["room_id"]
  room = kwargs["room"]

  sio.emit("table", { "table": room["table"], "room_id": room_id }, room=sid)

@sio.event
@require_room
@require_joined()
def winner_hand(sid, data, **kwargs):
  print("Request winner hand")
  room_id = kwargs["room_id"]
  room = kwargs["room"]
  
  if room["state"] != "END":
    sio.emit("info", {"msg": f"Party ({room_id}) did not end yet."}, room=sid)
    return
  sio.emit("winner_hand", {"hand": room["winner_hand"], "room_id": room_id}, room=sid)

@sio.event
@require_room
@require_joined()
@require_leader

def start(sid, data, **kwargs):
  print(f"Start perty / room")
  room_id = kwargs["room_id"]
  room = kwargs["room"]
  
  if room["thread"].is_alive():
    sio.emit("info", {"msg": f"Party ({room_id}) already started"}, room=sid)
    return
  room["state"] = "DEAL"
  room["thread"].start()
  sio.emit(
    "info",
    {"msg": f"Party started ({room_id})"},
    room=[USER_SID.get(player["user"]) for player in room["players"]])

@sio.event
@require_room
@require_joined()
@require_turn

def draw(sid, data, **kwargs):
  room_id = kwargs["room_id"]
  room = kwargs["room"]
  draw_from = data.get("from")

  print(f"Attempt to draw card", room_id, draw_from)
  player_turn_index = room["turn"]
  player_turn = room["players"][player_turn_index]
  
  if room["state"] != "TURN" or room["turn_state"] != "DRAW":
    sio.emit('info', {'msg': f'You are allowed to draw at this game state'}, room=sid)
    return

  if draw_from == "TABLE":
    if len(room["table"]) == 0:
      sio.emit('info', {'msg': f'Can\'t draw fron empty table.'}, room=sid)
      return
    card = room["table"].pop()
    room["drawn_from"] = "TABLE"
  else:
    # out of stock cards we reshuffle table into stock
    if len(room["stock"]) == 0:
      room["stock"] = shuffle(room[:-1])
      room["table"] = room["table"][-1]
      sio.emit(
        'info',
        {'msg': f'Reshuffle table into stock.'},
        room=[USER_SID.get(player["user"]) for player in room["players"]])

    card = room["stock"].pop()
    room["drawn_from"] = "STOCK"
  
  room["drawn_card"] = card
  room["turn_state"] = "SHED"
  player_turn["hand"].append(card)

  sio.emit(
    "hand",
    {"hand": player_turn["hand"], "room_id": room_id},
    room=sid)
  sio.emit(
    "table",
    {"table": room["table"], "room_id": room_id},
    room=[USER_SID.get(player["user"]) for player in room["players"]])

@sio.event
@require_room
@require_joined()
@require_turn

def shed(sid, data, **kwargs):
  room_id = kwargs["room_id"]
  room = kwargs["room"]
  print(f"Attempt to draw card")
  player_turn_index = room["turn"]
  player_turn = room["players"][player_turn_index]
  
  if room["state"] != "TURN" or room["turn_state"] != "SHED":
    sio.emit('info', {'msg': f'You are allowed to shed at this game state'}, room=sid)
    return
  if room["drawn_card"] == data["card"] and room["drawn_from"] == "TABLE":
    sio.emit('info', {'msg': f'You are allowed shed card u picked from table.'}, room=sid)
    return
  try:
    player_turn["hand"].remove(data["card"])
    room["table"].append(data["card"])
    room["turn"] = (room["turn"] + 1) % len(room["players"])
    room["turn_state"] = "DRAW"
    room["state"] = "TURN"
    
    sio.emit("hand", {"hand": player_turn["hand"], "room_id": room_id}, room=sid)
    sio.emit(
      "table",
      {"table": room["table"], "room_id": room_id},
      room=[USER_SID.get(player["user"]) for player in room["players"]])

  except:
    sio.emit('info', {'msg': f"The card {decode_card(data.get('card'))['number']}{decode_card(data.get('card'))['symbol']} is not in your hand"}, room=sid)
    return

def is_set(meld: List[str]):
  if len(meld) < 3:
    return False
  numbers = [decode_card(card)["number"] for card in meld]
  
  for number in numbers:
    if number != numbers[0]:
      return False
  return True

def is_run(meld: List[str]):
  if len(meld) < 3:
    return False
  symbols = [decode_card(card)["symbol"] for card in meld]
  for symbol in symbols:
    if symbol != symbols[0]:
      return False
  numbers = [decode_card(card)["number"] for card in meld]
  numbers = sorted(numbers)
  index = 1
  while index < len(numbers):
    if numbers[index] == 13 and numbers[index] != numbers[index - 1] + 2:
      return False
    if numbers[index] != 13 and numbers[index] != numbers[index - 1] + 1:
      return False
    index += 1
  return True

@sio.event
@require_room
@require_joined()
@require_turn

def show(sid, data, **kwargs):
  room_id = kwargs["room_id"]
  room = kwargs["room"]
  melds = data["melds"]
  
  player_turn = room["players"][room["turn"]]

  hand = [decode_card(card)["number"] for meld in melds for card in meld]
  
  if sorted(hand) != sorted([decode_card(card)["number"] for card in  player_turn["hand"]]):
    sio.emit('info', {'msg': f'Client and server hands not match !'}, room=sid)
    return
  
  for meld in melds:
    if not is_set(meld)  and not is_run(meld):
      sio.emit('info', {'msg': f'Your hand is not a wining hand'}, room=sid)
      return
    
  room["state"] = "END"
  room["winner_hand"] = melds

if __name__ == '__main__':
  # init_room("FIRST")
  run_simple("0.0.0.0", 5000, app, threaded=True)