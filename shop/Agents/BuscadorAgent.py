# -*- coding: utf-8 -*-
"""
Created on Fri Dec 27 15:58:13 2013

Esqueleto de agente usando los servicios web de Flask

/comm es la entrada para la recepcion de mensajes del agente
/Stop es la entrada que para el agente

Tiene una funcion AgentBehavior1 que se lanza como un thread concurrente

Asume que el agente de registro esta en el puerto 9000

@author: Marc i Arnau
"""

import argparse
import socket
import sys
sys.path.append('../')
from multiprocessing import Queue, Process
from threading import Thread
from typing import Literal

from flask import Flask, request
from rdflib import URIRef, XSD, RDF
from rdflib.plugins.sparql import prepareQuery

from AgentUtil.ACLMessages import *
from AgentUtil.Agent import Agent
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Logging import config_logger
from AgentUtil.OntoNamespaces import ECSDI, ACL, DSO

__author__ = 'ECSDIstore'

# Definimos los parametros de la linea de comandos
parser = argparse.ArgumentParser()
parser.add_argument('--open', help="Define si el servidor esta abierto al exterior o no", action='store_true',
                    default=False)
parser.add_argument('--port', type=int, help="Puerto de comunicacion del agente")
parser.add_argument('--dhost', default=socket.gethostname(), help="Host del agente de directorio")
parser.add_argument('--dport', type=int, help="Puerto de comunicacion del agente de directorio")

# Logging
logger = config_logger(level=1)

# Parsear los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = 9002
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


# Agent Namespace
agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente
BuscadorAgent = Agent('BuscadorAgent',
                       agn.BuscadorAgent,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global triplestore graph
dsgraph = Graph()

# Queue
cola1 = Queue()

# Flask stuff
app = Flask(__name__)

# función incrementar contador de mensajes
def getMessageCount():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

# Función que busca productos dependiendo de las restricciones que se le envian
def buscarProducto(content, grafoEntrada):
    # Extraemos las restricciones de busqueda que se nos pasan y creamos un contenedor de las restriciones
    # para su posterior procesamiento
    logger.info("Recibida peticion de busqueda")
    filtros = grafoEntrada.objects(content, ECSDI.FiltradoPor)
    directivasFiltradoras = {}
    for filtro in filtros:
        if grafoEntrada.value(subject=filtro, predicate=RDF.type) == ECSDI.FiltroPorNombre:
            nombre = grafoEntrada.value(subject=filtro, predicate=ECSDI.Nombre)
            directivasFiltradoras['Nombre'] = nombre
        elif grafoEntrada.value(subject=filtro, predicate=RDF.type) == ECSDI.FiltroPorPrecio:
            precioMax = grafoEntrada.value(subject=filtro, predicate=ECSDI.PrecioMaximo)
            precioMin = grafoEntrada.value(subject=filtro, predicate=ECSDI.PrecioMinimo)
            directivasFiltradoras['PrecioMax'] = precioMax
            directivasFiltradoras['PrecioMin'] = precioMin
    # Llamamos a una funcion que nos retorna un grafo con la información acorde al filtro establecido por el usuario
    resultadoComunicacion = findProductsByFilter(**directivasFiltradoras)
    return resultadoComunicacion

# Función que busca productos en la base de datos acorde a los filtros establecidos con anterioriad
def findProductsByFilter(Nombre=None,PrecioMin=0.0,PrecioMax=sys.float_info.max):
    logger.info("Haciendo resultado de busqueda")
    graph = Graph()
    ontologyFile = open('../data/BDProductos.owl')
    graph.parse(ontologyFile, format='turtle')

    addAnd = False
    logger.info("Buscando productos")
    query = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?Producto ?Nombre ?Precio ?Descripcion ?Peso
    where {
        ?Producto rdf:type ?type .
        FILTER (?type IN (default:Producto, default:ProductoExterno))
        ?Producto default:Nombre ?Nombre .
        ?Producto default:Precio ?Precio .
        ?Producto default:Descripcion ?Descripcion .
        ?Producto default:Peso ?Peso .
        FILTER("""

    if Nombre is not None:
        query += """?Nombre = '""" + Nombre + """'"""
        addAnd = True


    if PrecioMin is not None:
        if addAnd:
            query += """ && """
        query += """?Precio >= """ + str(PrecioMin)
        addAnd = True


    if PrecioMax is not None:
        if addAnd:
            query += """ && """
        query += """?Precio <= """ + str(PrecioMax)

    query += """)}"""

    graph_query = graph.query(query)
    products_graph = Graph()
    products_graph.bind('ECSDI', ECSDI)
    sujetoRespuesta = ECSDI['RespuestaDeBusqueda' + str(getMessageCount())]
    products_graph.add((sujetoRespuesta, RDF.type, ECSDI.RespuestaDeBusqueda))
    
    products_filtro = Graph()
    
    # Añadimos los productos resultantes de la búsqueda
    for product in graph_query:
        product_nombre = product.Nombre
        product_precio = product.Precio
        product_descripcion = product.Descripcion
        product_peso = product.Peso
        sujeto = product.Producto
        products_graph.add((sujeto, RDF.type, ECSDI.Producto))
        products_graph.add((sujeto, ECSDI.Nombre, Literal(product_nombre, datatype=XSD.string)))
        products_graph.add((sujeto, ECSDI.Precio, Literal(product_precio, datatype=XSD.float)))
        products_graph.add((sujeto, ECSDI.Descripcion, Literal(product_descripcion, datatype=XSD.string)))
        products_graph.add((sujeto, ECSDI.Peso, Literal(product_peso, datatype=XSD.float)))
        products_graph.add((sujetoRespuesta, ECSDI.Muestra, URIRef(sujeto)))
        
        # Grafo de los filtros
        sujetoFiltrado = ECSDI['ProductoFiltrado' + str(getMessageCount())]
        products_filtro.add((sujetoFiltrado, RDF.type, ECSDI.Producto))
        products_filtro.add((sujetoFiltrado, ECSDI.Nombre, Literal(product_nombre, datatype=XSD.string)))
        products_filtro.add((sujetoFiltrado, ECSDI.Precio, Literal(product_precio, datatype=XSD.float)))
        products_filtro.add((sujetoFiltrado, ECSDI.Descripcion, Literal(product_descripcion, datatype=XSD.string)))
        
    Thread(target=guardarFiltro, args=(products_filtro,)).start()

    logger.info("Respondiendo peticion de busqueda")
    return products_graph

def guardarFiltro(grafo):
    logger.info("Guardando filtro")
    ontologyFile = open('../data/BDFiltros')
    
    grafoFiltros = Graph()
    grafoFiltros.bind('default', ECSDI)
    grafoFiltros.parse(ontologyFile, format='turtle')
    grafoFiltros += grafo
    
    grafoFiltros.serialize(destination='../data/BDFiltros', format='turtle')
    logger.info("Filtro guardado")

@app.route("/comm")
def comunicacion():
    """
    Entrypoint de comunicacion
    """
    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(format='xml', data=message)
    
    message_properties = get_message_properties(grafoEntrada)
    
    resultadoComunicacion = None
    
    if message_properties is None:
        resultadoComunicacion = build_message(Graph(), ACL['not-understood'], sender=BuscadorAgent.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        if message_properties['performative'] != ACL.request:
            resultadoComunicacion = build_message(Graph(), ACL['not-understood'], sender=BuscadorAgent.uri, msgcnt=getMessageCount())
        else:
            # Extraemos el contenido que ha de ser una accion de la ontologia
            content = message_properties['content']
            accion = grafoEntrada.value(subject=content, predicate=RDF.type)
            
            # Si la acción es de tipo buscar producto
            if accion == ECSDI.BuscarProducto:
                resultadoComunicacion = buscarProducto(content, grafoEntrada)
    
    return resultadoComunicacion.serialize(format='xml'), 200
    

@app.route("/Stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def tidyup():
    """
    Acciones previas a parar el agente

    """
    pass


def buscadorbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    registerAgent(BuscadorAgent, DirectoryAgent, BuscadorAgent.uri, getMessageCount())

def getMessageCount():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=buscadorbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')
