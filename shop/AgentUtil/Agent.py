"""
.. module:: Agent

Agent
******
###
:Description: Agent
  Clase para guardar los atributos de un agente

"""

__author__ = 'bejar'


class Agent():
    def __init__(self, name, uri, address, stop):
        self.name = name
        self.uri = uri
        self.address = address
        self.stop = stop

class AgentCL():
    def __init__(self, name, uri, address, diference, stop):
        self.name = name
        self.uri = uri
        self.address = address
        self.diference = diference
        self.stop = stop