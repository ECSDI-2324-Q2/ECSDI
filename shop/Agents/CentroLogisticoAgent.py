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
import socket
import threading
import sys

sys.path.append('../')
from multiprocessing import Queue, Process
from time import sleep

from flask import Flask, request
from rdflib import URIRef, XSD, Namespace, Literal

from AgentUtil.ACLMessages import *
from AgentUtil.Agent import Agent
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Logging import config_logger
from AgentUtil.OntoNamespaces import ECSDI
from AgentUtil.OntoNamespaces import ACL, DSO
from rdflib.namespace import FOAF, RDF, RDFS

__author__ = 'Arnau'

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
    port = 9011
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
CentroLogisticoAgent = Agent('CentroLogisticoAgent',
                    agn.CentroLogisticoAgent,
                    'http://%s:%d/comm' % (hostname, port),
                    'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

CentroLogisticoDirectoryAgent = Agent('CentroLogisticoDirectoryAgent',
                       agn.CentroLogisticoDirectoryAgent,
                       'http://%s:9010/Register' % (dhostname),
                       'http://%s:9010/Stop' % (dhostname))

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

def responderPeticionEnvio(grafoEntrada, content):
    logger.info("Recibida peticion envio a centro logistico")
    prioritat = grafoEntrada.value(subject=content, predicate=ECSDI.Prioridad)


    relacion = grafoEntrada.value(subject=content, predicate=ECSDI.EnvioDe)
    direccion = grafoEntrada.value(subject=relacion, predicate=ECSDI.Destino)
    direccion2 = grafoEntrada.value(subject=direccion, predicate=ECSDI.Direccion)
    codigopostal = grafoEntrada.value(subject=direccion, predicate=ECSDI.CodigoPostal)

    logger.info("Haciendo respuesta a envio desde centro logistico")
    grafoFaltan = Graph()
    grafoFaltan.bind('default', ECSDI)
    contentR = ECSDI['RespuestaEnvioDesdeCentroLogistico' + str(getMessageCount())]

    grafoFaltan.add((contentR, RDF.type, ECSDI.RespuestaEnvioDesdeCentroLogistico))
    grafoFaltan.add((contentR, ECSDI.Prioridad, Literal(prioritat, datatype=XSD.int)))

    sujetoCompra = ECSDI['Compra' + str(getMessageCount())]

    grafoFaltan.add((contentR, ECSDI.Faltan, URIRef(sujetoCompra)))
    grafoFaltan.add((sujetoCompra, RDF.type, ECSDI.Compra))
    grafoFaltan.add((sujetoCompra, ECSDI.Destino, URIRef(direccion)))

    grafoFaltan.add((direccion, RDF.type, ECSDI.Direccion))
    grafoFaltan.add((direccion, ECSDI.Direccion, Literal(direccion2, datatype=XSD.string)))
    grafoFaltan.add((direccion, ECSDI.CodigoPostal, Literal(codigopostal, datatype=XSD.int)))

    graph = Graph()
    ontologyFile = open('../data/ProductosCL1')
    graph.parse(ontologyFile, format='turtle')
    logger.info("Registrando productos pendientes")
    ontologyFile = open("../data/ProductosPendientes1DB")
    grafoPendientes = Graph()
    grafoPendientes.parse(ontologyFile, format='turtle')

    grafoEnviar = Graph()
    grafoEnviar.bind('default', ECSDI)

    for producto in grafoEntrada.objects(subject=relacion, predicate=ECSDI.Contiene):
        nombreP = grafoEntrada.value(subject=producto, predicate=ECSDI.Nombre)
        print("Comprobando stock para " + nombreP)
        query = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                            PREFIX owl: <http://www.w3.org/2002/07/owl#>
                            PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
                            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                            SELECT ?Stock ?Producto ?Nombre ?Descripcion ?Precio ?Peso ?UnidadesEnStock
                            where {
                                ?Stock rdf:type default:Stock .
                                ?Stock default:UnidadesEnStock ?UnidadesEnStock .
                                ?Stock default:Tiene ?Producto .
                                ?Producto default:Nombre ?Nombre .
                                ?Producto default:Descripcion ?Descripcion .
                                ?Producto default:Precio ?Precio .
                                ?Producto default:Peso ?Peso .
                                FILTER("""

        if nombreP is not None:
            query += """?Nombre = '""" + nombreP + """'"""

        query += """)}"""

        graph_query = graph.query(query)

        for stock in graph_query:
            unitats = stock.UnidadesEnStock
            producto = stock.Producto
            descripcion = stock.Descripcion
            nombre = stock.Nombre
            precio = stock.Precio
            peso = stock.Peso

            if unitats == 0:
                logger.info("No hay stock de " + nombre + "!")
                logger.info("Añadimos " + nombre + " a la respuesta a envio desde centro logistico")
                grafoFaltan.add((producto, RDF.type, ECSDI.Producto))
                grafoFaltan.add((producto, ECSDI.Descripcion, Literal(descripcion, datatype=XSD.string)))
                grafoFaltan.add((producto, ECSDI.Nombre, Literal(nombre, datatype=XSD.string)))
                grafoFaltan.add((producto, ECSDI.Precio, Literal(precio, datatype=XSD.string)))
                grafoFaltan.add((producto, ECSDI.Peso, Literal(peso, datatype=XSD.string)))
                grafoFaltan.add((sujetoCompra, ECSDI.Contiene, URIRef(producto)))

            else:
                logger.info("Tenemos stock de " + nombre + "!")
                logger.info("Añadiendo " + nombre +" a productos pendientes")
                contentEnviar = ECSDI['ProductoPendiente' + str(getMessageCount())]
                grafoEnviar.add((contentEnviar, RDF.type, ECSDI.ProductoPendiente))
                grafoEnviar.add((contentEnviar, ECSDI.Nombre, Literal(nombre, datatype=XSD.string)))
                grafoEnviar.add((contentEnviar, ECSDI.Peso, Literal(peso, datatype=XSD.float)))
                grafoEnviar.add((contentEnviar, ECSDI.Prioridad, Literal(prioritat, datatype=XSD.int)))

                grafoEnviar.add((direccion, RDF.type, ECSDI.Direccion))
                grafoEnviar.add((direccion, ECSDI.Direccion, Literal(direccion2, datatype=XSD.string)))
                grafoEnviar.add((direccion, ECSDI.CodigoPostal, Literal(codigopostal, datatype=XSD.int)))
                grafoEnviar.add((contentEnviar, ECSDI.EnviarA, URIRef(direccion)))
                logger.info("Disminuyendo stock para " + nombre)
                graph.remove((stock.Stock, ECSDI.UnidadesEnStock, None))
                uni = int(unitats) - 1
                graph.add((stock.Stock, ECSDI.UnidadesEnStock, Literal(uni, datatype=XSD.int)))
                logger.info("Stock disminuido para " + nombre)

        if len(graph_query) == 0:
            logger.info("No hay stock de " + nombreP + "!")
            logger.info("Añadimos " + nombreP + " a la respuesta a envio desde centro logistico")
            descripcion = grafoEntrada.value(subject=producto, predicate=ECSDI.Descripcion)
            nombre = grafoEntrada.value(subject=producto, predicate=ECSDI.Nombre)
            precio = grafoEntrada.value(subject=producto, predicate=ECSDI.Precio)
            peso = grafoEntrada.value(subject=producto, predicate=ECSDI.Peso)
            grafoFaltan.add((producto, RDF.type, ECSDI.Producto))
            grafoFaltan.add((producto, ECSDI.Descripcion, Literal(descripcion, datatype=XSD.string)))
            grafoFaltan.add((producto, ECSDI.Nombre, Literal(nombre, datatype=XSD.string)))
            grafoFaltan.add((producto, ECSDI.Precio, Literal(precio, datatype=XSD.string)))
            grafoFaltan.add((producto, ECSDI.Peso, Literal(peso, datatype=XSD.string)))
            grafoFaltan.add((sujetoCompra, ECSDI.Contiene, URIRef(producto)))

    logger.info("Comprobación de stock finalizada")
    grafoPendientes += grafoEnviar
    grafoPendientes.serialize(destination="../data/ProductosPendientes1DB", format='turtle')
    logger.info("Registro de productos pendientes finalizado")
    graph.serialize(destination="../data/ProductosCL1", format='turtle')

    logger.info("Devolviendo respuesta a envio desde centro logístico")
    return grafoFaltan

def crearLotes():
    graph = Graph()

    ontologyFile = open("../data/ProductosPendientes1DB")
    graph.parse(ontologyFile, format='turtle')

    nouLote = Graph()
    nouLote.bind('default', ECSDI)
    logger.info("Haciendo lote de productos")
    contentLote = ECSDI['LoteProductos' + str(getMessageCount())]
    nouLote.add((contentLote, RDF.type, ECSDI.LoteProductos))
    pesoLote = 0

    for producto_pendiente in graph.subjects(predicate=RDF.type, object=ECSDI.ProductoPendiente):
        if int(graph.value(subject=producto_pendiente, predicate=ECSDI.Prioridad)) == 1:
            logger.info("Encontrado producto pendiente con prioridad 1")
            ## Agafem els atributs del producte pendent
            producto_direccion = graph.value(subject=producto_pendiente, predicate=ECSDI.EnviarA)
            producto_nombre = graph.value(subject=producto_pendiente, predicate=ECSDI.Nombre)
            peso = graph.value(subject=producto_pendiente, predicate=ECSDI.Peso)
            producto_adress = graph.value(subject=producto_direccion, predicate=ECSDI.Direccion)
            producto_codigo_postal = graph.value(subject=producto_direccion, predicate=ECSDI.CodigoPostal)

            ## Afegim el producte al graf nouLote
            nouLote.add((producto_pendiente, RDF.type, ECSDI.ProductoPendiente))
            nouLote.add((producto_pendiente, ECSDI.Nombre, Literal(producto_nombre, datatype=XSD.string)))
            nouLote.add((producto_direccion, RDF.type, ECSDI.Direccion))
            nouLote.add((producto_direccion, ECSDI.Direccion, Literal(producto_adress, datatype=XSD.string)))
            nouLote.add((producto_direccion, ECSDI.CodigoPostal, Literal(producto_codigo_postal, datatype=XSD.int)))
            nouLote.add((producto_pendiente, ECSDI.EnviarA, producto_direccion))
            nouLote.add((contentLote, ECSDI.CompuestoPor, producto_pendiente))

            pesoLote = float(peso) + pesoLote

            for item in graph.objects(subject=producto_pendiente):
                graph.remove((producto_pendiente, None, item))

            for item in graph.objects(subject=producto_direccion):
                graph.remove((producto_direccion, None, item))

        else:
            logger.info("Encontrado producto pendiente con prioridad mayor a 1")
            print(str(graph.value(subject=producto_pendiente, predicate=ECSDI.Nombre)))
            prioridad = int(graph.value(subject=producto_pendiente, predicate=ECSDI.Prioridad))
            logger.info("Disminuyendo prioridad en 1")
            graph.remove((producto_pendiente, ECSDI.Prioridad, None))
            prioridad = prioridad - 1
            graph.add((producto_pendiente, ECSDI.Prioridad, Literal(prioridad, datatype=XSD.int)))

    nouLote.add((contentLote, ECSDI.Peso, Literal(pesoLote, datatype=XSD.float)))

    if pesoLote != 0:
        thread = threading.Thread(target=enviarLote, args=(nouLote,contentLote,))
        thread.start()

    graph.serialize(destination="../data/ProductosPendientes1DB", format='turtle')

    return

def enviarLote(nouLote, contentLote):
    # Obtenemos información del directorio de transportistas
    transportistaDirectory = getAgentInfo(agn.TransportistaDirectoryAgent, DirectoryAgent, CentroLogisticoAgent,
                                         getMessageCount())
    # Obtenemos todos los transportistas
    agentes = getTransportistas(agn.TransportistaAgent, transportistaDirectory, CentroLogisticoAgent,
                                              getMessageCount())

    grafoPeticion = nouLote
    grafoPeticion.bind('default', ECSDI)
    logger.info("Haciendo peticion oferta transporte")
    contentPeticion = ECSDI['PeticionOfertaTransporte' + str(getMessageCount())]
    grafoPeticion.add((contentPeticion, RDF.type, ECSDI.PeticionOfertaTransporte))
    grafoPeticion.add((contentPeticion, ECSDI.DeLote, URIRef(contentLote)))

    ofertas = []
    i = 0

    for transportista in agentes:
        logger.info("Enviando peticion oferta transporte " + str(i))
        respuesta = send_message(
            build_message(grafoPeticion, perf=ACL.request, sender=CentroLogisticoAgent.uri, receiver=transportista.uri,
                          msgcnt=getMessageCount(), content=contentPeticion), transportista.address)
        logger.info("Recibida respuesta oferta transporte " + str(i))
        for o in respuesta.objects(predicate=ECSDI.Precio):
            ofertas.append(o)
        i += 1

    min = 0
    imin = -1
    i = 0

    for o in ofertas:
        if o > min:
            imin = i
            min = o
        i += 1


    if imin != -1:
        logger.info("Oferta " + str(imin) + " escogida")
        transportista = agentes[imin]
        confirmarTransporte(transportista, nouLote, contentLote)

def confirmarTransporte(transportista, nouLote, contentLote):
    grafoPeticion = nouLote
    grafoPeticion.remove((None, RDF.type, ECSDI.PeticionOfertaTransporte))
    for item in grafoPeticion.subjects(RDF.type, ACL.FipaAclMessage):
        grafoPeticion.remove((item, None, None))
    grafoPeticion.bind('default', ECSDI)
    logger.info("Haciendo peticion envio lote")
    contentPeticion = ECSDI['PeticionEnvioLote' + str(getMessageCount())]
    grafoPeticion.add((contentPeticion, RDF.type, ECSDI.PeticionEnvioLote))
    grafoPeticion.add((contentPeticion, ECSDI.PendienteDeSerEnviado, URIRef(contentLote)))
    logger.info("Enviando peticion envio lote")
    respuesta = send_message(
        build_message(grafoPeticion, perf=ACL.request, sender=CentroLogisticoAgent.uri, receiver=transportista.uri,
                      msgcnt=getMessageCount(), content=contentPeticion), transportista.address)
    logger.info("Enviada peticion envio lote")

def crearLotesThread():
    logger.info("Iniciando creación rutinaria de lotes")
    thread = threading.Thread(target=crearLotes)
    thread.start()
    thread.join()
    logger.info("Creación rutinaria de lotes finalizada")
    sleep(500)

    crearLotesThread()

def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio
    :param gmess:
    :return:
    """

    logger.info('Nos registramos')
    registerCentroLogistico(CentroLogisticoAgent, CentroLogisticoDirectoryAgent, CentroLogisticoAgent.uri, getMessageCount(),8028)
    #registerAgent(CentroLogisticoAgent, DirectoryAgent, CentroLogisticoAgent.uri, getMessageCount())

@app.route("/comm")
def communication():
    """
    Communication Entrypoint
    """

    global dsGraph

    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message)

    messageProp = get_message_properties(grafoEntrada)
    res = Graph()

    if messageProp is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        res = build_message(Graph(), ACL['not-understood'], sender=CentroLogisticoAgent.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        if messageProp['performative'] != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            res = build_message(Graph(),
                               ACL['not-understood'],
                               sender=CentroLogisticoDirectoryAgent.uri,
                               msgcnt=getMessageCount())
        else:
            content = messageProp['content']
            # Averiguamos el tipo de la accion
            accion = grafoEntrada.value(subject=content, predicate=RDF.type)

            if accion == ECSDI.PeticionEnvioACentroLogistico:

                for item in grafoEntrada.subjects(RDF.type, ACL.FipaAclMessage):
                    grafoEntrada.remove((item, None, None))

                faltan = responderPeticionEnvio(grafoEntrada, content)
                res = faltan

    serialize = res.serialize(format='xml')
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

def centroLogistico1Behaviour(queue):

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    register_message()

if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    thread = threading.Thread(target=crearLotesThread)
    thread.start()
    ab1 = Process(target=centroLogistico1Behaviour, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    thread.join()
    print('The End')