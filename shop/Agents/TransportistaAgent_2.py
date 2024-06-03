# -*- coding: utf-8 -*-

"""
Agente usando los servicios web de Flask
/comm es la entrada para la recepcion de mensajes del agente
/Stop es la entrada que para el agente
Tiene una funcion AgentBehavior1 que se lanza como un thread concurrente
Asume que el agente de registro esta en el puerto 9000
"""
import argparse
from datetime import datetime, timedelta
import random
import socket
import sys
sys.path.append('../')
from multiprocessing import Queue, Process
from threading import Thread

from flask import Flask, request
from rdflib import URIRef, XSD, Namespace, Literal

from AgentUtil.ACLMessages import *
from AgentUtil.Agent import Agent
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Logging import config_logger
from AgentUtil.OntoNamespaces import ECSDI
from AgentUtil.OntoNamespaces import ACL, DSO
from rdflib.namespace import RDF, FOAF

__author__ = 'ECSDIstore'

# Definimos los parametros de la linea de comandos
parser = argparse.ArgumentParser()
parser.add_argument('--open', help="Define si el servidor est abierto al exterior o no", action='store_true',
                    default=False)
parser.add_argument('--port', type=int, help="Puerto de comunicacion del agente")
parser.add_argument('--dhost', default=socket.gethostname(), help="Host del agente de directorio")
parser.add_argument('--dport', type=int, help="Puerto de comunicacion del agente de directorio")

# Logging
logger = config_logger(level=1)

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = 9012
else:
    port = args.port

if args.open is None:
    hostname = '0.0.0.0'
else:
    hostname = socket.gethostname()

if args.dport is None:
    dport = 9006
else:
    dport = args.dport

if args.dhost is None:
    dhostname = socket.gethostname()
else:
    dhostname = args.dhost

# AGENT ATTRIBUTES ----------------------------------------------------------------------------------------

# Agent Namespace
agn = Namespace("http://www.agentes.org#")

# Message Count
mss_cnt = 0

# Datos del Agente
TransportistaAgent = Agent('TransportistaAgent2',
                    agn.TransportistaAgent2,
                    'http://%s:%d/comm' % (hostname, port),
                    'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgentTransportistes = Agent('DirectoryAgentTransportistes',
                       agn.DirectoryAgentTransportistes,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global triplestore graph
dsGraph = Graph()

# Queue
queue = Queue()

# Flask app
app = Flask(__name__)

#función incremental de numero de mensajes
def getMessageCount():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

def realizarTransporte(grafoEntrada, content):
    logger.info('Recibida Peticion Envio Lote')
    delote = None
    for s, p, o in grafoEntrada.triples((None, RDF.type, ECSDI.DeLote)):
        delote = s
    prioridad = grafoEntrada.value(subject=delote, predicate=ECSDI.Prioridad)
    dias = 1
    if prioridad == 2:
        dias = random.randint(3, 5)
    elif prioridad == 3:
        dias = random.randint(1, 20)

    logger.info('Su pedido llegara el dia:' + str(datetime.now() + timedelta(days=dias)))
    logger.info('Soy el transportista:' + TransportistaAgent.name)

def realizarOfertaTransporte(grafoEntrada, content):
    logger.info("Recibida petición oferta")
    lote = grafoEntrada.value(subject=content, predicate=ECSDI.DeLote)
    peso = grafoEntrada.value(subject=lote, predicate=ECSDI.Peso)

    precio = calcularPrecio(float(peso))

    grafoOferta = Graph()
    grafoOferta.bind('default', ECSDI)
    logger.info("Haciendo oferta de transporte")
    contentOferta = ECSDI['RespuestaOfertaTransporte'+ str(getMessageCount())]
    grafoOferta.add((contentOferta, RDF.type, ECSDI.RespuestaOfertaTransporte))
    grafoOferta.add((contentOferta, ECSDI.Precio, Literal(precio, datatype=XSD.float)))
    logger.info("Devolvemos oferta de transporte")
    return grafoOferta

def calcularPrecio(peso):
    logger.info("Calculando oferta")
    #int random = random.randint(1, 10)
    oferta = 3.0 + peso*3
    logger.info("Oferta calculada: " + str(oferta))
    return oferta

#funcion llamada en /comm
@app.route("/comm")
def communication():
    logger.info('Peticion de comunicacion recibida')
    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message, format='xml')

    messageProperties = get_message_properties(grafoEntrada)

    resultadoComunicacion = Graph()

    if messageProperties is None:
        # Respondemos que no hemos entendido el mensaje
        resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                              sender=TransportistaAgent.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        if messageProperties['performative'] != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                                  sender=DirectoryAgentTransportistes.uri, msgcnt=getMessageCount())
        else:
            # Extraemos el contenido que ha de ser una accion de la ontologia definida en Protege
            content = messageProperties['content']
            accion = grafoEntrada.value(subject=content, predicate=RDF.type)

            # # Si la acción es de tipo peticionTrasporte emprendemos las acciones consequentes
            if accion == ECSDI.PeticionTransporte:

                # Eliminar los ACLMessage
                for item in grafoEntrada.subjects(RDF.type, ACL.FipaAclMessage):
                    grafoEntrada.remove((item, None, None))

                realizarTransporte(grafoEntrada, content)

            else:
                if accion == ECSDI.PeticionOfertaTransporte:
                    # Eliminar los ACLMessage
                    for item in grafoEntrada.subjects(RDF.type, ACL.FipaAclMessage):
                        grafoEntrada.remove((item, None, None))
                    resultadoComunicacion = realizarOfertaTransporte(grafoEntrada, content)
            

    serialize = resultadoComunicacion.serialize(format='xml')
    logger.info('Respondemos a la peticion')
    return serialize, 200

@app.route("/Stop")
def stop():
    """
    Entrypoint to the agent
    :return: string
    """
    shutdown_server()
    return "Stopping server"

def TransportistaBehavior(queue):

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    registerAgent(TransportistaAgent, DirectoryAgentTransportistes, agn.TransportistaAgent, getMessageCount())

if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    ab1 = Process(target=TransportistaBehavior, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    print('The End')