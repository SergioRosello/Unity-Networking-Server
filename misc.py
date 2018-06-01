import math


def split(l, size):
	"""
	Divide una lista en porciones de un tamaño dado
	:param l: Lista a dividir
	:param size: Tamaño deseado
	:return: Lista de listas del tamaño deseado (o menor)
	"""
	arrs = []
	while len(l) > size:
		pice = l[:size]
		arrs.append(pice)
		l = l[size:]
	arrs.append(l)
	return arrs


def distance(x1, y1, x2, y2):
	"""
	Calcula la distancia entre dos puntos
	:param x1: Coordenada x del primer punto
	:param y1: Coordenada y del primer punto
	:param x2: Coordenada x del segundo punto
	:param y2: Coordenada y del segundo punto
	:return: Distancia entre los puntos
	"""
	return math.sqrt(((x1 - x2) ** 2) + ((y1 - y2) ** 2))


def estimate_current_position(last_position, velocity, time_delta):
	"""
	Calcula la posición actual del un objeto
	:param last_position: Última posición recibida
	:param velocity: Velocidad que llevaba el objeto
	:param time_delta: Tiempo que ha pasado desde que se recibió la última posición
	:return:
	"""
	return {
		'x': last_position['x'] + velocity['x'] * time_delta,
		'y': last_position['y'] + velocity['y'] * time_delta,
	}
