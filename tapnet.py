import hashlib
import json
from datetime import datetime
from socket import socket, AF_INET, SOCK_DGRAM
from threading import Thread
from time import sleep

from misc import split


class TapNet:
	DATAGRAM_ACK = 0
	DATAGRAM_NORMAL = 1
	DATAGRAM_RELIABLE = 2

	CHUNK_SIZE = 1000  # Tamaño de los chunks, en bytes

	def __init__(self, address):
		self.address = address
		self.datagramId = 0  # Id del próximo datagrama a enviar
		self.datagrams_awating_ack = {}  # Paquetes 'confiables' enviados a la espera de confirmación
		self.sock = socket(AF_INET, SOCK_DGRAM)
		self.response_handler = None

	def start(self):
		print('Starting server on  {}'.format(self.address))
		self.sock = socket(AF_INET, SOCK_DGRAM)
		self.sock.bind(self.address)
		listen_loop = Thread(target=self.listen_loop)
		listen_loop.start()
		datagram_check = Thread(target=self.datagram_check)
		datagram_check.start()

	def send_ack(self, datagram_id, to):
		"""
		Envía un ACK
		:param datagram_id: ID del datagrama del cliente que estamos confirmando
		:param to: Cliente al que vamos a enviar el ACK
		:return:
		"""
		ack = self.DATAGRAM_ACK.to_bytes(
			4, 'little'
		) + datagram_id.to_bytes(
			4, 'little'
		)
		self.sock.sendto(ack, to)

	def send_json(self, json_to_send, data_type, to):
		"""
		Envía un json a través del socket
		:param json_to_send: JSON a enviar
		:param data_type: Tipo de datos a enviar, ACK, NORMAL o RELIABLE
		:param to: Cliente al que vamos a enviar los datos
		"""
		# TODO: Codificar correctamente las cabeceras
		json_bytes = json.dumps(json_to_send).encode(encoding='utf-8')
		splitted_bytes = split(json_bytes, self.CHUNK_SIZE)
		number_of_chunks = len(splitted_bytes)

		datagrams_to_send = []

		for i, part in enumerate(splitted_bytes):
			m = hashlib.sha256()
			m.update(part)

			part = data_type.to_bytes(
				4, 'little'
			) + self.datagramId.to_bytes(
				4, 'little'
			) + m.digest(

			) + number_of_chunks.to_bytes(
				4, 'little'
			) + i.to_bytes(
				4, 'little'
			) + part

			self.sock.sendto(part, to)
			datagrams_to_send.append(part)

		if data_type == self.DATAGRAM_RELIABLE:
			# Apuntamos estos paquetes como 'pendientes de confirmar su recepción'
			self.datagrams_awating_ack[self.datagramId] = {
				'time': datetime.now(),
				'retries': 0,
				'datagrams': datagrams_to_send,
				'to': to
			}
		self.datagramId += 1

	def listen_loop(self):
		"""
		Escucha las peticiones entrantes
		"""
		# TODO: La conversión de bytes a int se hace con int.from_bytes(bytes, 'little')
		while 1:
			data, address = self.sock.recvfrom(4096)
			if data:
				datagram_type = 0  # TODO: 4 primeros bytes: tipo de datagrama
				datagram_id = 0  # TODO: 4 siguientes bytes: id de datagrama

				if datagram_type == self.DATAGRAM_ACK:
					# Si es un ACK, vemos qué paquete es el que se ha recibido
					chunk_number = 0  # TODO: 4 bytes desde el 8: chunk_number
					if datagram_id in self.datagrams_awating_ack:
						# Lo quitamos de la lista de "esperando ack"
						self.datagrams_awating_ack[datagram_id]['datagrams'][chunk_number] = None
				else:
					content = data[40:]
					expected_sha256 = data[8:40]
					check = hashlib.sha256()
					check.update(content)
					obtained_sha256 = check.digest()

					if expected_sha256 == obtained_sha256:
						if datagram_type == self.DATAGRAM_RELIABLE:
							# Tenemos que enviar ACK para confirmar la recepción
							self.send_ack(datagram_id, address)

						received_json = json.loads(content.decode(encoding='utf-8'))
						self.response_handler(received_json, address)

	def datagram_check(self):
		"""
		Comprueba que el estado de los envíos de los datagramas confiables. Realiza su trabajo en otro thread.
		"""
		while 1:
			# Quitamos todos aquellos que hayamos reintentado demasiadas veces
			self.datagrams_awating_ack = {
				k: v for k, v in self.datagrams_awating_ack.items() if
				[e for e in v['datagrams'] if e] and v['retries'] < 5
			}

			now = datetime.now()

			# Reenviamos los que haga falta
			for k, v in self.datagrams_awating_ack.items():
				if (now - v['time']).seconds > 1:
					v['time'] = now
					v['retries'] += 1
					for datagram in v['datagrams']:
						if datagram:
							self.sock.sendto(datagram, v['to'])
			sleep(.5)
