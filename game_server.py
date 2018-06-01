from datetime import datetime
from threading import Thread
from random import randint, uniform
import json
from time import sleep

from misc import  distance, estimate_current_position
from tapnet import TapNet

INITIAL_REQUEST = "initial"
UPDATE_REQUEST = "update"
CHEST_REQUEST = "picked_chest"
DISCONNECT_REQUEST = "disconnect"


DATE_FORMAT = '%Y/%m/%d%H:%M:%S.%f'
BOMB_RANGE = 3


class GameServer:
	def __init__(self):
		self.MAP_WIDTH = 40
		self.MAP_HEIGHT = 25

		self.current_map = []
		self.current_players = {}
		self.current_player_index = 0
		self.datagramId = 0
		self.bombs = []
		self.chests = []
		self.current_timer = 90

		self.min_chest_spawn_interval = 2
		self.max_chest_spawn_interval = 6

		self.min_bomb_spawn_interval = 2
		self.max_bomb_spawn_interval = 5

		self.datagrams_awating_ack = {}  # Paquetes 'confiables' enviados a la espera de confirmación
		self.map_changes = []  # Información con los cambios que sufre el mapa, para poder sincronizarlos con los clientes

		self.server = None

	def generate_map(self):
		"""
		Genera el mapa de la partida
		:return:
		"""
		obstacle_id = 1
		current_map = []
		for i in range(self.MAP_WIDTH):
			col = []
			for j in range(self.MAP_HEIGHT):
				if randint(0, 100) < 80:
					col.append(0)
				else:
					col.append(obstacle_id)
					obstacle_id += 1
			current_map.append(col)
		self.current_map = current_map

	def is_map_empty(self, x, y):
		"""
		Nos dice si el mapa está libre en una posición
		:param x: Coordenada x de la posición
		:param y: Coordenada y de la posición
		:return: True si está libre, False en caso contrario
		"""
		return not self.current_map[x][y]

	def get_random_spawn_position(self):
		"""
		Obtiene una posición del mapa que esté libre, de forma aleatoria
		:return: Diccionario con la coordenada obtenida del formato con los valores 'x' e 'y'
		"""
		x = randint(0, self.MAP_WIDTH - 1)
		y = randint(0, self.MAP_HEIGHT - 1)

		while not self.is_map_empty(x, y):
			x = randint(0, self.MAP_WIDTH - 1)
			y = randint(0, self.MAP_HEIGHT - 1)

		return {'x': x, 'y': y}

	def chest_spawn(self):
		"""
		Genera los cofres. Realiza su trabajo en otro thread.
		"""
		# TODO: Implementar con locks
		chest_id = 0
		while self.current_timer > -1:
			sleep(
				uniform(
					self.min_chest_spawn_interval,
					self.max_chest_spawn_interval
				) / len(self.current_players) if len(self.current_players) else 1
			)
			if self.current_players:
				chest = self.get_random_spawn_position()
				chest['id'] = chest_id
				self.chests.append(chest)
				chest_id += 1

	def bomb_spawn(self):
		"""
		Genera las bombas. Realiza su trabajo en otro thread.
		"""
		# TODO: Implementar con locks
		bomb_id = 0
		while self.current_timer > -1:
			sleep(
				uniform(
					self.min_bomb_spawn_interval, self.max_bomb_spawn_interval
				) / len(self.current_players) if len(self.current_players) else 1
			)
			if self.current_players:
				bomb = self.get_random_spawn_position()
				bomb['timer'] = 5
				bomb['id'] = bomb_id
				self.bombs.append(bomb)
				bomb_id += 1

	def player_check(self):
		"""
		Elimina a los jugadores que estén caídos. Realiza su trabajo en otro thread.
		"""
		# TODO: Implementar con locks
		while self.current_timer > -1:
			for k, v in list(self.current_players.items()):
				last_player_update_str = v.get('serverTimeStamp', '')
				last_player_update_object = datetime.strptime(last_player_update_str, DATE_FORMAT)
				time_elapsed = (datetime.now() - last_player_update_object).total_seconds()
				if time_elapsed > 1:
					del(self.current_players[k])
			sleep(2)

	"""
	Se ejecuta en el hilo que lleva la cuenta atrás de las bombas
	"""
	def bomb_check(self):
		"""
		Comprueba el estado de las bombas activas. Realiza su trabajo en otro thread.
		"""
		# TODO: Implementar con locks
		# TODO: Decrementar el timer de las bombas
		# TODO: Excepciones
		while self.current_timer > -1:
			for bomb in self.bombs:
				bomb['timer'] -= 0.1

			for bomb in self.bombs:
				if bomb['timer'] <= 0:
					bomb_x = bomb['x']
					bomb_y = bomb['y']

					destroyed_tiles = []

					minx = bomb_x - BOMB_RANGE if bomb_x - BOMB_RANGE >= 0 else 0
					miny = bomb_y - BOMB_RANGE if bomb_y - BOMB_RANGE >= 0 else 0
					maxx = bomb_x + BOMB_RANGE if bomb_x + BOMB_RANGE < self.MAP_WIDTH else self.MAP_WIDTH - 1
					maxy = bomb_y + BOMB_RANGE if bomb_y + BOMB_RANGE < self.MAP_HEIGHT else self.MAP_HEIGHT - 1

					# Ver qué tiles se rompen

					for checked_x in range(minx, maxx):
						for checked_y in range(miny, maxy):
							if self.current_map[checked_x][checked_y]:
								if distance(bomb_x, bomb_y, checked_x, checked_y) <= BOMB_RANGE:
									destroyed_tiles.append(self.current_map[checked_x][checked_y])
									self.current_map[checked_x][checked_y] = 0

					if destroyed_tiles:
						self.map_changes.append(destroyed_tiles)

					# Ver si damos a algun jugador:
					current_players = self.current_players
					for k, v in current_players.items():
						player_pos = estimate_current_position(
							v['position'],
							v['velocity'],
							(datetime.now() - datetime.strptime(v.get('serverTimeStamp', ''), DATE_FORMAT)).total_seconds()
						)
						if distance(bomb_x, bomb_y, player_pos['x'], player_pos['y']) <= BOMB_RANGE:
							v['health'] = 0
					self.current_players = current_players

			self.bombs = [bomb for bomb in self.bombs if bomb['timer'] > 0]

	def handle_json(self, received_json, sender):
		"""
		Reacciona en función al JSON recibido
		:param received_json: JSON que hemos recibido
		:param sender: Quién nos envía los datos
		"""
		if received_json['type'] == INITIAL_REQUEST:
			data_to_send = {
				'type': INITIAL_REQUEST,
				'map': self.current_map,
				'width': self.MAP_WIDTH,
				'map_version': len(self.map_changes),
				'height': self.MAP_HEIGHT,
				'spawn': self.get_random_spawn_position(),
				'playerId': self.current_player_index
			}

			current_players = self.current_players
			current_players[self.current_player_index] = {
				'score': 0,
				'playerName': received_json["playerName"],
				'position': {'x': 0, 'y': 0},
				'velocity': {'x': 0, 'y': 0},
				'health': 1,
				'serverTimeStamp': datetime.now().strftime(DATE_FORMAT)
			}
			self.current_players = current_players

			self.current_player_index += 1
			self.server.send_json(data_to_send, TapNet.DATAGRAM_RELIABLE, sender)
		elif received_json['type'] == UPDATE_REQUEST:
			# Un jugador está actualizando los datos. Actualizo el estado de la partida
			player = self.current_players.get(received_json.get('playerId', ''), {})
			if player:
				last_player_update = player.get(
					'clientTimeStamp', '')
				current_update = received_json.get('clientTimeStamp', '')

				if current_update > last_player_update:
					# print('JSON: {}'.format(received_json))
					new_player_data = {
						'position': received_json['position'],
						'velocity': received_json['velocity'],
						'clientTimeStamp': received_json['clientTimeStamp'],
						'serverTimeStamp': datetime.now().strftime(DATE_FORMAT)
					}
					self.current_players[received_json['playerId']].update(new_player_data)
				client_map_version = received_json["mapVersion"]
				changes = self.map_changes[client_map_version:]

				# Enviamos los últimos datos al jugador
				data_to_send = {
					'type': UPDATE_REQUEST,
					'state': {
						'players': self.current_players,
						'bombs': self.bombs,
						'chests': self.chests,
						'map_changes': changes,
						'timer': self.current_timer
					}
				}
				self.server.send_json(data_to_send, TapNet.DATAGRAM_NORMAL, sender)
		elif received_json['type'] == CHEST_REQUEST:
			# Un jugador solicita coger un cofre
			if [c for c in self.chests if c['id'] == received_json['chestId']]:
				# Si el cofre existe, confirmamos al jugador que ha cogido el cofre y actualizamos su score
				self.chests = [c for c in self.chests if c['id'] != received_json['chestId']]
				self.current_players[received_json['playerId']]['score'] += 1
		elif received_json['type'] == DISCONNECT_REQUEST:
			# Un jugador se está desconectando, lo quitamos de la lista de jugadores
			player_id = received_json.get('playerId', -1)
			if player_id in self.safe_get_players():
				self.lock_players.acquire()
				del(self.current_players[player_id])
				self.lock_players.release()
				data_to_send = {
					'type': DISCONNECT_REQUEST
				}
				self.server.send_json(data_to_send, TapNet.DATAGRAM_NORMAL, sender)

	def countdown(self):
		"""
		Realiza la cuenta atrás del timer de la partida. Realiza su trabajo en otro thread.
		"""
		while self.current_timer > -1:
			self.current_timer -= 1
			sleep(1)

	def start(self):
		# TODO: Que el servidor vuelva a arrancar correctamente cuando termine la ronda y empecemos otra
		"""
		Arranca el servidor
		"""
		server_address = ('0.0.0.0', 10000)
		self.server = TapNet(server_address)

		while 1:
			# En cada iteración, reiniciamos los valores
			self.generate_map()
			self.current_players = {}
			self.bombs = []
			self.chests = []
			self.current_timer = 90
			self.datagrams_awating_ack = {}
			self.map_changes = []

			threads = []

			chest_thread = Thread(target=self.chest_spawn)
			threads.append(chest_thread)
			bomb_thread = Thread(target=self.bomb_spawn)
			threads.append(bomb_thread)
			bomb_check = Thread(target=self.bomb_check)
			threads.append(bomb_check)
			player_check = Thread(target=self.player_check)
			threads.append(player_check)
			countdown_thread = Thread(target=self.countdown)
			threads.append(countdown_thread)

			self.server.start()

			for t in threads:
				t.start()

			for t in threads:
				t.join()
