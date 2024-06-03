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
    port = 9013
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
CentroLogisticoAgent = Agent('CentroLogisticoAgent2',
                    agn.CentroLogisticoAgent2,
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

def find_existing_lote(graph, codigo_postal, prioridad):
    for lote in graph.subjects(RDF.type, ECSDI.Lote):
        if (graph.value(lote, ECSDI.Prioridad) == Literal(prioridad, datatype=XSD.int) and
            graph.value(lote, ECSDI.CodigoPostal) == Literal(codigo_postal, datatype=XSD.int)):
            return lote
    return None

def create_new_lote(graph, codigo_postal, prioridad):
    content_lote = ECSDI['Lote' + str(getMessageCount())]
    graph.add((content_lote, RDF.type, ECSDI.Lote))
    graph.add((content_lote, ECSDI.CodigoPostal, Literal(codigo_postal, datatype=XSD.int)))
    graph.add((content_lote, ECSDI.Prioridad, Literal(prioridad, datatype=XSD.int)))
    return content_lote, 0

def add_product_to_lote(graph, content_lote, producto, peso_lote):
    producto_resource = ECSDI['Producto' + str(getMessageCount())]
    graph.add((producto_resource, RDF.type, ECSDI.Producto))
    graph.add((producto_resource, ECSDI.Nombre, Literal(producto['nombre'], datatype=XSD.string)))
    graph.add((producto_resource, ECSDI.Descripcion, Literal(producto['descripcion'], datatype=XSD.string)))
    graph.add((producto_resource, ECSDI.Precio, Literal(producto['precio'], datatype=XSD.float)))
    graph.add((producto_resource, ECSDI.Peso, Literal(producto['peso'], datatype=XSD.float)))

    graph.add((content_lote, ECSDI.CompuestoPor, producto_resource))

    peso_lote += float(producto['peso'])
    return peso_lote

def crear_lotes(codigo_postal, prioridad, productos_compra):
    graph = Graph()
    datos_lotes = open("../Data/LotesPendientesCL2DB.owl")
    graph.parse(datos_lotes, format='turtle')
    
    lote_existente = find_existing_lote(graph, codigo_postal, prioridad)
    
    if lote_existente:
        logger.info("Lote existente encontrado, añadiendo productos al lote existente")
        content_lote = lote_existente
        peso_lote = float(graph.value(content_lote, ECSDI.Peso))
    else:
        logger.info("Creando nuevo lote de productos")
        content_lote, peso_lote = create_new_lote(graph, codigo_postal, prioridad)
    
    for producto in productos_compra:
        peso_lote = add_product_to_lote(graph, content_lote, producto, peso_lote)

    graph.set((content_lote, ECSDI.Peso, Literal(peso_lote, datatype=XSD.float)))
    
    graph.serialize(destination="../Data/LotesPendientesCL2DB.owl", format='turtle')

    return
    
def extract_product_data(grafoEntrada, producto_resource):
    producto_dict = {}
    for p, o in grafoEntrada.predicate_objects(subject=producto_resource):
        if p == ECSDI.Nombre:
            producto_dict['nombre'] = str(o)
        elif p == ECSDI.Descripcion:
            producto_dict['descripcion'] = str(o)
        elif p == ECSDI.Precio:
            producto_dict['precio'] = str(o)
        elif p == ECSDI.Peso:
            producto_dict['peso'] = str(o)
        
        producto_dict['id'] = str(producto_resource)
    return producto_dict

def responderPeticionEnvio(grafoEntrada, content):
    logger.info("Recibida peticion envio a centro logistico")

    # Initialize variables
    codigo_postal = None
    prioridad = None
    productos_compra = []

    # Iterate over triples in the graph
    for s, p, o in grafoEntrada:
        if p == ECSDI.CodigoPostal:
            codigo_postal = o
        elif p == ECSDI.Prioridad:
            prioridad = o
        elif p == ECSDI.Envia:
            productos_compra.append(o)

    print ('Prioridad: ', prioridad)

    # Check if all the required data is present
    if codigo_postal is None or prioridad is None or len(productos_compra) == 0:
        logger.info("No se ha recibido toda la informacion necesaria")
        return None
    
    # Crear Lote
    logger.info("Creando lote de productos")
    productos = [extract_product_data(grafoEntrada, ECSDI['Producto' + str(producto.value)]) for producto in productos_compra]

    sujeto = ECSDI['PeticionEnvioACentroLogistico']
    grafoEntrada.remove((sujeto, ECSDI.Envia, None))

    crear_lotes(codigo_postal, prioridad, productos)

    return grafoEntrada

def create_product(graph, producto_pendiente, producto_direccion, producto_nombre, producto_adress, producto_codigo_postal, contentLote):
    graph.add((producto_pendiente, RDF.type, ECSDI.ProductoPendiente))
    graph.add((producto_pendiente, ECSDI.Nombre, Literal(producto_nombre, datatype=XSD.string)))
    graph.add((producto_direccion, RDF.type, ECSDI.Direccion))
    graph.add((producto_direccion, ECSDI.Direccion, Literal(producto_adress, datatype=XSD.string)))
    graph.add((producto_direccion, ECSDI.CodigoPostal, Literal(producto_codigo_postal, datatype=XSD.int)))
    graph.add((producto_pendiente, ECSDI.EnviarA, producto_direccion))
    graph.add((contentLote, ECSDI.CompuestoPor, producto_pendiente))

def remove_product(graph, producto_pendiente, producto_direccion):
    for item in graph.objects(subject=producto_pendiente):
        graph.remove((producto_pendiente, None, item))

    for item in graph.objects(subject=producto_direccion):
        graph.remove((producto_direccion, None, item))

def decrease_priority(graph, producto_pendiente):
    prioridad = int(graph.value(subject=producto_pendiente, predicate=ECSDI.Prioridad))
    graph.remove((producto_pendiente, ECSDI.Prioridad, None))
    prioridad = prioridad - 1
    graph.add((producto_pendiente, ECSDI.Prioridad, Literal(prioridad, datatype=XSD.int)))

def crearLotes():
    graph = Graph()
    ontologyFile = open("../Data/LotesPendientesCL2DB.owl")
    graph.parse(ontologyFile, format='turtle')

    nouLote = Graph()
    nouLote.bind('default', ECSDI)
    contentLote = ECSDI['LoteProductos' + str(getMessageCount())]
    nouLote.add((contentLote, RDF.type, ECSDI.LoteProductos))
    pesoLote = 0

    for producto_pendiente in graph.subjects(predicate=RDF.type, object=ECSDI.ProductoPendiente):
        if int(graph.value(subject=producto_pendiente, predicate=ECSDI.Prioridad)) == 1:
            producto_direccion = graph.value(subject=producto_pendiente, predicate=ECSDI.EnviarA)
            producto_nombre = graph.value(subject=producto_pendiente, predicate=ECSDI.Nombre)
            peso = graph.value(subject=producto_pendiente, predicate=ECSDI.Peso)
            producto_adress = graph.value(subject=producto_direccion, predicate=ECSDI.Direccion)
            producto_codigo_postal = graph.value(subject=producto_direccion, predicate=ECSDI.CodigoPostal)

            create_product(nouLote, producto_pendiente, producto_direccion, producto_nombre, producto_adress, producto_codigo_postal, contentLote)

            pesoLote = float(peso) + pesoLote

            remove_product(graph, producto_pendiente, producto_direccion)
        else:
            decrease_priority(graph, producto_pendiente)

    nouLote.add((contentLote, ECSDI.Peso, Literal(pesoLote, datatype=XSD.float)))

    if pesoLote != 0:
        thread = threading.Thread(target=enviarLote, args=(nouLote,contentLote,))
        thread.start()

    graph.serialize(destination="../Data/LotesPendientesCL2DB.owl", format='turtle')

    return

def create_request_graph(nouLote, contentLote):
    grafoPeticion = nouLote
    grafoPeticion.bind('default', ECSDI)
    contentPeticion = ECSDI['PeticionOfertaTransporte' + str(getMessageCount())]
    grafoPeticion.add((contentPeticion, RDF.type, ECSDI.PeticionOfertaTransporte))
    grafoPeticion.add((contentPeticion, ECSDI.DeLote, URIRef(contentLote)))
    return grafoPeticion, contentPeticion

def get_transport_offers(agentes, grafoPeticion, contentPeticion):
    ofertas = []
    for i, transportista in enumerate(agentes):
        logger.info(f"Enviando peticion oferta transporte {i}")
        respuesta = send_message(
            build_message(grafoPeticion, perf=ACL.request, sender=CentroLogisticoAgent.uri, receiver=transportista.uri,
                          msgcnt=getMessageCount(), content=contentPeticion), transportista.address)
        logger.info(f"Recibida respuesta oferta transporte {i}")
        for o in respuesta.objects(predicate=ECSDI.Precio):
            ofertas.append(o)
    return ofertas

def enviarLote(nouLote, contentLote):
    # Obtenemos información del directorio de transportistas
    transportistaDirectory = getAgentInfo(agn.DirectoryAgentTransportistes, DirectoryAgent, CentroLogisticoAgent,
                                         getMessageCount())
    # Obtenemos todos los transportistas
    agentes = getTransportistas(agn.TransportistaAgent, transportistaDirectory, CentroLogisticoAgent,
                                              getMessageCount())

    grafoPeticion, contentPeticion = create_request_graph(nouLote, contentLote)
    ofertas = get_transport_offers(agentes, grafoPeticion, contentPeticion)

    imin, max_oferta = min(enumerate(ofertas), key=lambda oferta: oferta[1])

    if imin != -1:
        logger.info(f"Oferta {imin} escogida")
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
    grafoPeticion.add((contentPeticion, RDF.type, ECSDI.PeticionTransporte))
    grafoPeticion.add((contentPeticion, ECSDI.PendienteDeSerEnviado, URIRef(contentLote)))
    logger.info("Enviando peticion envio lote")
    respuesta = send_message(
        build_message(grafoPeticion, perf=ACL.request, sender=CentroLogisticoAgent.uri, receiver=transportista.uri,
                      msgcnt=getMessageCount(), content=contentPeticion), transportista.address)
    
    logger.info("Enviada peticion envio lote")

def crear_grafo_lote(lote_info):
    nuevo_grafo = Graph()
    nuevo_grafo.bind('default', ECSDI)
    
    # Añadir el lote al nuevo grafo
    lote_uri = lote_info['lote']
    nuevo_grafo.add((lote_uri, RDF.type, ECSDI.Lote))
    nuevo_grafo.add((lote_uri, ECSDI.Prioridad, Literal(lote_info['prioridad'], datatype=XSD.int)))
    nuevo_grafo.add((lote_uri, ECSDI.CodigoPostal, Literal(lote_info['codigo_postal'], datatype=XSD.int)))
    nuevo_grafo.add((lote_uri, ECSDI.Peso, Literal(lote_info['peso'], datatype=XSD.float)))
    
    for producto in lote_info['productos']:
        nuevo_grafo.add((lote_uri, ECSDI.CompuestoPor, producto))
    
    return nuevo_grafo

def get_lote_data(g, lote):
    """Extracts lote data from the graph."""
    prioridad = int(g.value(subject=lote, predicate=ECSDI.Prioridad))
    codigo_postal = int(g.value(subject=lote, predicate=ECSDI.CodigoPostal))
    productos = list(g.objects(subject=lote, predicate=ECSDI.CompuestoPor))
    peso = sum(float(peso) for peso in g.objects(subject=lote, predicate=ECSDI.Peso))

    return {
        'lote': lote,
        'prioridad': prioridad,
        'codigo_postal': codigo_postal,
        'productos': productos,
        'num_productos': len(productos),
        'peso': peso
    }

def sort_lotes(lotes):
    """Sorts lotes based on priority and number of products."""
    return sorted(lotes, key=lambda x: (x['prioridad'], x['num_productos']), reverse=True)

def escoger_lotes():
    g = Graph()
    g.parse('../Data/LotesPendientesCL2DB.owl', format='turtle')

    lotes = [get_lote_data(g, lote) for lote in g.subjects(predicate=ECSDI.Prioridad)]
    lotes = sort_lotes(lotes)

    if lotes:
        lote = crear_grafo_lote(lotes[0])
        enviarLote(lote, lotes[0]['lote'])
    else:
        return None
    
    borrar_lotes_enviados()

def borrar_lotes_enviados():
    logger.info("Borrando lotes enviados")
    graph = Graph()
    # Serialize the empty graph to the file
    graph.serialize(destination="../Data/LotesPendientesCL2DB.owl", format='turtle')


def escoger_lotes_periodico():
    logger.info("Iniciando seleccion de lotes periodica")
    thread = threading.Thread(target=escoger_lotes)
    thread.start()
    thread.join()
    logger.info("Lotes seleccionados para su envío")
    sleep(120)

    escoger_lotes_periodico()

def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio
    :param gmess:
    :return:
    """

    logger.info('Nos registramos')
    registerCentroLogistico(CentroLogisticoAgent, CentroLogisticoDirectoryAgent, agn.CentroLogisticoAgent, getMessageCount(),3029, '../data/ProductosCL2.owl')

@app.route("/comm")
def communication():
    """
    Communication Entrypoint
    """

    global dsGraph

    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(format='xml', data=message)

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
            subject = None
            for s, p, o in grafoEntrada.triples((None, RDF.type, ECSDI.PeticionEnvioACentroLogistico)):
                subject = s

            # Averiguamos el tipo de la accion
            accion = grafoEntrada.value(subject=subject, predicate=RDF.type)

            if accion == ECSDI.PeticionEnvioACentroLogistico:

                for item in grafoEntrada.subjects(RDF.type, ACL.FipaAclMessage):
                    grafoEntrada.remove((item, None, None))

                faltan = responderPeticionEnvio(grafoEntrada, subject)
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
    thread = threading.Thread(target=escoger_lotes_periodico)
    thread.start()
    ab1 = Process(target=centroLogistico1Behaviour, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    thread.join()
    print('The End')