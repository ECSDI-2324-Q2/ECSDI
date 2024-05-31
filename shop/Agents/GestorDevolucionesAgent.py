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
import datetime
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
    port = 9042
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
GestorDevolucionesAgent = Agent('GestorDevoluciones',
                    agn.GestorDevoluciones,
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

# Función inclremental de numero de mensajes
def getMessageCount():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

# Función encargada del retorno de productos distribuyendo el trabajo en diversos threads
def retornarProductos(content, grafoEntrada):
    logger.info("Recibida peticion de retorno")
    direccion = grafoEntrada.objects(predicate=ECSDI.Direccion)
    direccionRetorno = None
    for d in direccion:
        direccionRetorno = d
    codigo = grafoEntrada.objects(predicate=ECSDI.CodigoPostal)
    codigoPostal = None
    for c in codigo:
        codigoPostal = c
    print(codigoPostal, direccionRetorno)
    thread1 = Thread(target=solicitarRecogida, args=(direccionRetorno, codigoPostal))
    thread1.start()
    thread2 = Thread(target=borrarProductosRetornados, args=(grafoEntrada, content))
    thread2.start()
    resultadoComunicacion = Graph()
    logger.info("Respondiendo peticion de retorno")
    return resultadoComunicacion

# Función que atiende la petición de retorno de todos los productos enviados por un usuario con una tarjeta
def solicitarProductosEnviados(content, grafoEntrada):
    logger.info("Recibida peticion de productos enviados")
    graph = Graph()
    ontologyFile = open('../data/EnviosDB')
    tarjeta = None
    tarjetaObjects = grafoEntrada.objects(subject=content, predicate=ECSDI.Tarjeta)
    for t in tarjetaObjects:
        tarjeta = t
    graph.parse(ontologyFile, format='turtle')
    logger.info("Buscamos productos comprados por " + tarjeta)
    query = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                            PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
                            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                            SELECT ?PeticionEnvio ?Producto ?Nombre ?Precio ?Descripcion ?Peso ?Tarjeta ?Compra ?FechaEntrega
                            where {
                                ?PeticionEnvio rdf:type default:PeticionEnvio .
                                ?PeticionEnvio default:Tarjeta ?Tarjeta .
                                ?PeticionEnvio default:De ?Compra .
                                ?PeticionEnvio default:FechaEntrega ?FechaEntrega .
                                ?Compra default:Contiene ?Producto .       
                                ?Producto default:Nombre ?Nombre .
                                ?Producto default:Precio ?Precio .
                                ?Producto default:Descripcion ?Descripcion .
                                ?Producto default:Peso ?Peso .
                                FILTER("""
    query += """?Tarjeta = """ + str(tarjeta)
    query += """ && ?FechaEntrega > '""" + str(datetime.now() - datetime.timedelta(days=15)) + """'^^xsd:date"""
    query += """ && ?FechaEntrega < '""" + str(datetime.now() + datetime.timedelta(days=1)) + """'^^xsd:date"""
    query += """)}"""
    resultadoConsulta = graph.query(query)
    resultadoComunicacion = Graph()
    # Añadimos los productos enviados que coincidan
    for product in resultadoConsulta:
        product_nombre = product.Nombre
        product_precio = product.Precio
        product_descripcion = product.Descripcion
        product_peso = product.Peso
        sujeto = ECSDI['ProductoEnviado' + str(getMessageCount())]
        resultadoComunicacion.add((sujeto, RDF.type, ECSDI.ProductoEnviado))
        resultadoComunicacion.add((sujeto, ECSDI.Nombre, Literal(product_nombre, datatype=XSD.string)))
        resultadoComunicacion.add((sujeto, ECSDI.Precio, Literal(product_precio, datatype=XSD.float)))
        resultadoComunicacion.add((sujeto, ECSDI.Descripcion, Literal(product_descripcion, datatype=XSD.string)))
        resultadoComunicacion.add((sujeto, ECSDI.Peso, Literal(product_peso, datatype=XSD.float)))
        resultadoComunicacion.add((sujeto, ECSDI.EsDe, product.Compra))
    logger.info("Respondiendo peticion de valoracion")
    return resultadoComunicacion

# Función que elimina productos devueltos de la base de datos
def borrarProductosRetornados(grafo, content):
    # Eliminamos los productos devueltos de envios
    logger.info("Registramos la devolucion")
    ontologyFile = open('../data/EnviosDB')

    products = grafo.objects(subject=content, predicate= ECSDI.Auna)

    grafoEnvios = Graph()
    grafoEnvios.bind('default', ECSDI)
    grafoEnvios.parse(ontologyFile, format='turtle')

    for product in products:
        compra = grafo.value(subject=product, predicate=ECSDI.EsDe)
        nombre = grafo.value(subject=product, predicate=ECSDI.Nombre)

        query = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?Producto ?Nombre  
            WHERE {  
                ?Producto rdf:type default:Producto . 
                ?Producto default:Nombre ?Nombre .
                FILTER("""

        query += """?Nombre = '""" + nombre + """'"""
        query += """)}"""

        graph_query = grafoEnvios.query(query)

        producto = None
        for p in graph_query:
            producto = p.Producto

        grafoEnvios.remove((compra, None, producto))

    # Guardem el graf
    grafoEnvios.serialize(destination='../data/EnviosDB', format='turtle')
    logger.info("Registro de devolucion finalizado")

# Función que solicita a un Transportista prefijado la recogida de un conjunto de productos a una dirección determinada
def solicitarRecogida(direccionRetorno,codigoPostal):
    logger.info("Haciendo peticion de recoger devolucion")
    peticion = Graph()
    accion = ECSDI["PeticionRecogerDevolucion"+str(getMessageCount())]
    peticion.add((accion,RDF.type,ECSDI.PeticionRecogerDevolucion))
    sujetoDireccion = ECSDI['Direccion' + str(getMessageCount())]
    peticion.add((sujetoDireccion, RDF.type, ECSDI.Direccion))
    peticion.add((sujetoDireccion, ECSDI.Direccion, Literal(direccionRetorno, datatype=XSD.string)))
    peticion.add((sujetoDireccion, ECSDI.CodigoPostal, Literal(codigoPostal, datatype=XSD.int)))
    peticion.add((accion, ECSDI.Desde, URIRef(sujetoDireccion)))

    # Solicitamos informacion del transportista de devoluciones
    agente = getAgentInfo(agn.TransportistaDevolucionesAgent, DirectoryAgent, GestorDevolucionesAgent, getMessageCount())

    # Enviamos peticion de recoger devolucion al transportista
    logger.info("Enviando peticion de recoger devolucion")
    grafoBusqueda = send_message(
        build_message(peticion, perf=ACL.request, sender=GestorDevolucionesAgent.uri, receiver=agente.uri,
                      msgcnt=getMessageCount(),
                      content=accion), agente.address)
    logger.info("Enviada peticion de recoger devolucion")


@app.route("/comm")
def communication():
    """
    Communication Entrypoint
    """
    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message)

    messageProperties = get_message_properties(grafoEntrada)

    resultadoComunicacion = None

    if messageProperties is None:
        # Respondemos que no hemos entendido el mensaje
        resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                              sender=GestorDevolucionesAgent.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        if messageProperties['performative'] != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                                  sender=DirectoryAgent.uri, msgcnt=getMessageCount())
        else:
            content = messageProperties['content']
            accion = grafoEntrada.value(subject=content, predicate=RDF.type)
            # Si la acción es de tipo peticiónCompra emprendemos las acciones consequentes
            if accion == ECSDI.PeticionProductosEnviados:
                resultadoComunicacion = solicitarProductosEnviados(content, grafoEntrada)
            elif accion == ECSDI.PeticionRetorno:
                resultadoComunicacion = retornarProductos(content, grafoEntrada)

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

def tidyUp():
    """
    Previous actions for the agent.
    """

    global queue
    queue.put(0)

    pass

def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio
    :param gmess:
    :return:
    """

    logger.info('Nos registramos')
    gr = registerAgent(GestorDevolucionesAgent, DirectoryAgent, GestorDevolucionesAgent.uri, getMessageCount())
    return gr

def DevolvedorBehaviour(queue):

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    gr = register_message()

if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    ab1 = Process(target=DevolvedorBehaviour, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    print('The End')