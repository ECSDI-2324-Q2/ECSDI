# -*- coding: utf-8 -*-

"""
Agente usando los servicios web de Flask
/comm es la entrada para la recepcion de mensajes del agente
/Stop es la entrada que para el agente
Tiene una funcion AgentBehavior1 que se lanza como un thread concurrente
Asume que el agente de registro esta en el puerto 9000
"""
import argparse
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
    port = 9087
else:
    port = args.port

if args.open is None:
    hostname = '0.0.0.0'
else:
    hostname = socket.gethostname()

if args.dport is None:
    dport = 9000
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

# Data Agent
# Datos del Agente
GestorExternoAgent = Agent('GestorExterno',
                    agn.GestorExterno,
                    'http://%s:%d/comm' % (hostname, port),
                    'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global triplestore graph
dsGraph = Graph()

# Queue
queue = Queue()

# Flask app
app = Flask(__name__)

#función inclremental de numero de mensajes
def getMessageCount():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

# Función que agrega un Producto Externo a la base de datos
def añadirProducto(content, grafoEntrada):
    logger.info("Recibida peticion de agregar productos")
    for item in grafoEntrada.subjects(RDF.type, ACL.FipaAclMessage):
        grafoEntrada.remove((item, None, None))
    thread = Thread(target=procesarProductoExterno, args=(grafoEntrada,))
    thread.start()
    resultadoComunicacion = Graph()
    logger.info("Respondiendo peticion de agregar producto")
    return resultadoComunicacion

# Función que procesa un producto externo
def procesarProductoExterno(graph):
    nombre = None
    peso = None
    tarjeta = None
    precio= None
    descripcion = None
    gestionExterna = False
    for a,b,c in graph:
        if b == ECSDI.Nombre:
            nombre = c
        elif b == ECSDI.Descripcion:
            descripcion = c
        elif b == ECSDI.Peso:
            peso = c
        elif b == ECSDI.GestionExterna:
            gestionExterna = c
        elif b == ECSDI.Precio:
            precio = c
        elif b == ECSDI.Tarjeta:
            tarjeta = c

    logger.info("Registrando producto " + nombre + " con descripcion: " + descripcion + " que pesa: " + peso + " con precio: " + precio)
    # Añadimos el producto externo a la base de datos de productos del sistema
    graph = Graph()
    ontologyFile = open('../data/BDProductos.owl')
    graph.parse(ontologyFile, format='turtle')
    graph.bind("default", ECSDI)
    sujeto = ECSDI['ProductoExterno' + str(getMessageCount())]
    graph.add((sujeto, RDF.type, ECSDI.ProductoExterno))
    graph.add((sujeto, ECSDI.Nombre, Literal(nombre, datatype=XSD.string)))
    graph.add((sujeto, ECSDI.Precio, Literal(precio, datatype=XSD.float)))
    graph.add((sujeto, ECSDI.Descripcion, Literal(descripcion, datatype=XSD.string)))
    graph.add((sujeto, ECSDI.Tarjeta, Literal(tarjeta, datatype=XSD.string)))
    graph.add((sujeto, ECSDI.GestionExterna, Literal(gestionExterna, datatype=XSD.boolean)))
    graph.add((sujeto, ECSDI.Peso, Literal(peso, datatype=XSD.float)))

    graph.serialize(destination='../data/BDProductos.owl', format='turtle')
    logger.info("Registro de nuevo producto finalizado")

#funcion llamada en /comm
@app.route("/comm")
def communication():
    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message, format='xml')

    messageProperties = get_message_properties(grafoEntrada)

    resultadoComunicacion = None

    if messageProperties is None:
        # Respondemos que no hemos entendido el mensaje
        resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                              sender=GestorExternoAgent.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        if messageProperties['performative'] != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                                  sender=DirectoryAgent.uri, msgcnt=getMessageCount())
        else:
            # Extraemos el contenido que ha de ser una accion de la ontologia definida en Protege
            content = messageProperties['content']
            accion = grafoEntrada.value(subject=content, predicate=RDF.type)

            # Si la acción es de tipo busqueda emprendemos las acciones consequentes
            if accion == ECSDI.PeticionAgregarProductoExterno:
                resultadoComunicacion = añadirProducto(content, grafoEntrada)



    serialize = resultadoComunicacion.serialize(format='xml')
    return serialize, 200

@app.route("/Stop")
def stop():
    """
    Entrypoint to the agent
    :return: string
    """

    tidyUp()
    shutdown_server()
    return "Stopping server"

#función llamada antes de cerrar el servidor
def tidyUp():
    """
    Previous actions for the agent.
    """

    global queue
    queue.put(0)

    pass

#funcion llamada al principio de un agente
def filterBehavior(queue):

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    registerAgent(GestorExternoAgent, DirectoryAgent, GestorExternoAgent.uri, getMessageCount())

if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    ab1 = Process(target=filterBehavior, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    print('The End')