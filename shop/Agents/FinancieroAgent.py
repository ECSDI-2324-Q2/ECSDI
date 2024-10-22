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

__author__ = 'Miquel'

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
    port = 9004
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

# Datos del Agente
FinancieroAgent = Agent('FinancieroAgent',
                    agn.FinancieroAgent,
                    'http://%s:%d/comm' % (hostname, port),
                    'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.DirectoryAgent,
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

def registrarFactura(grafoEntrada):
    logger.info("Registrando la factura")

    grafoFacturas = Graph()
    grafoFacturas.bind('default', ECSDI)

    with open('../data/FacturasDB') as ontologyFile:
        grafoFacturas.parse(ontologyFile, format='turtle')

    grafoFacturas += grafoEntrada

    # Guardem el graf
    grafoFacturas.serialize(destination='../data/FacturasDB', format='turtle')
    logger.info("Registro de factura finalizado")

def generar_factura(grafoEntrada, content):
    logger.info("Generando factura")

    tarjeta = grafoEntrada.value(subject=content, predicate=ECSDI.Tarjeta)
    compra = grafoEntrada.value(subject=content, predicate=ECSDI.De)

    grafoFactura = Graph()
    grafoFactura.bind('default', ECSDI)

    # Crear factura
    sujeto = ECSDI['Factura' + str(getMessageCount())]
    grafoFactura.add((sujeto, RDF.type, ECSDI.Factura))
    grafoFactura.add((sujeto, ECSDI.Tarjeta, Literal(tarjeta, datatype=XSD.int)))

    precioTotal = 0
    productos = grafoEntrada.objects(subject=compra, predicate=ECSDI.Contiene)
    for producto in productos:
        nombreProducto = grafoEntrada.value(subject=producto, predicate=ECSDI.Nombre)
        precioProducto = float(grafoEntrada.value(subject=producto, predicate=ECSDI.Precio))

        grafoFactura.add((producto, RDF.type, ECSDI.Producto))
        grafoFactura.add((producto, ECSDI.Nombre, Literal(nombreProducto, datatype=XSD.string)))
        grafoFactura.add((producto, ECSDI.Precio, Literal(precioProducto, datatype=XSD.float)))
        grafoFactura.add((sujeto, ECSDI.Facturando, URIRef(producto)))

        precioTotal += precioProducto

    grafoFactura.add((sujeto, ECSDI.PrecioTotal, Literal(precioTotal, datatype=XSD.float)))

    # Guardar Factura
    Thread(target=registrarFactura, args=(grafoFactura,)).start()

    logger.info("Devolviendo factura")
    return grafoFactura


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
                                              sender=FinancieroAgent.uri, msgcnt=getMessageCount())
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

            # Si la acción es de tipo peticiónCompra emprendemos las acciones consequentes
            if accion == ECSDI.GenerarFactura:

                # Eliminar los ACLMessage
                for item in grafoEntrada.subjects(RDF.type, ACL.FipaAclMessage):
                    grafoEntrada.remove((item, None, None))

                resultadoComunicacion = generar_factura(grafoEntrada, content)

            

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

def FinancieroBehavior(queue):

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    registerAgent(FinancieroAgent, DirectoryAgent, FinancieroAgent.uri, getMessageCount())

if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    ab1 = Process(target=FinancieroBehavior, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    print('The End')