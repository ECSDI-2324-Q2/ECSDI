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
    ontologyFile = open('../data/FacturasDB')

    grafoFacturas = Graph()
    grafoFacturas.bind('default', ECSDI)
    grafoFacturas.parse(ontologyFile, format='turtle')
    grafoFacturas += grafoEntrada

    # Guardem el graf
    grafoFacturas.serialize(destination='../data/FacturasDB', format='turtle')
    logger.info("Registro de factura finalizado")

def generar_factura(grafoEntrada, content):
    logger.info("Generando factura")

    tarjeta = grafoEntrada.value(subject=content, predicate=ECSDI.Tarjeta)
    grafoFactura = Graph()
    grafoFactura.bind('default', ECSDI)

    # Crear factura
    sujeto = ECSDI['Factura' + str(getMessageCount())]
    grafoFactura.add((sujeto, RDF.type, ECSDI.Factura))
    grafoFactura.add((sujeto, ECSDI.Tarjeta, Literal(tarjeta, datatype=XSD.int)))

    compra = grafoEntrada.value(subject=content, predicate=ECSDI.De)

    precioTotal = 0
    for producto in grafoEntrada.objects(subject=compra, predicate=ECSDI.Contiene):
        grafoFactura.add((producto, RDF.type, ECSDI.Producto))

        nombreProducto = grafoEntrada.value(subject=producto, predicate=ECSDI.Nombre)
        grafoFactura.add((producto, ECSDI.Nombre, Literal(nombreProducto, datatype=XSD.string)))

        precioProducto = grafoEntrada.value(subject=producto, predicate=ECSDI.Precio)
        grafoFactura.add((producto, ECSDI.Precio, Literal(float(precioProducto), datatype=XSD.float)))
        precioTotal += float(precioProducto)

        grafoFactura.add((sujeto, ECSDI.Facturando, URIRef(producto)))

    grafoFactura.add((sujeto, ECSDI.PrecioTotal, Literal(precioTotal, datatype=XSD.float)))

    # Guardar Factura
    thread = Thread(target=registrarFactura, args=(grafoFactura,))
    thread.start()
    
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

            print(accion)
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
    gr = register_message()

def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio

    :param gmess:
    :return:
    """

    logger.info('Nos registramos')

    global mss_cnt

    gmess = Graph()

    # Construimos el mensaje de registro
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    reg_obj = agn[FinancieroAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, FinancieroAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(FinancieroAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(FinancieroAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.FinancieroAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=FinancieroAgent.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

    return gr

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