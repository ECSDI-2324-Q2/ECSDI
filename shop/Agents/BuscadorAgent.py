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

from multiprocessing import Process, Queue
import socket

from rdflib import Namespace, Graph
from flask import Flask

from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Agent import Agent
from AgentUtil.ACLMessages import *

__author__ = 'ECSDIstore'

# Configuration stuff
hostname = socket.gethostname()
port = 9010

agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

Buscadoragent = Agent('Buscadoragent',
                       agn.Buscadoragent,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)

# Global triplestore graph
dsgraph = Graph()

cola1 = Queue()

# Flask stuff
app = Flask(__name__)


# Función que busca productos dependiendo de las restricciones que se le envian
def buscarProducto(content, grafoEntrada):
    # Extraemos las restricciones de busqueda que se nos pasan y creamos un contenedor de las restriciones
    # para su posterior procesamiento
    logger.info("Recibida peticion de busqueda")
    restricciones = grafoEntrada.objects(content, ECSDI.RestringidaPor)
    directivasRestrictivas = {}
    for restriccion in restricciones:
        if grafoEntrada.value(subject=restriccion, predicate=RDF.type) == ECSDI.RestriccionDeNombre:
            nombre = grafoEntrada.value(subject=restriccion, predicate=ECSDI.Nombre)
            directivasRestrictivas['Nombre'] = nombre
        elif grafoEntrada.value(subject=restriccion, predicate=RDF.type) == ECSDI.RestriccionDePrecio:
            precioMax = grafoEntrada.value(subject=restriccion, predicate=ECSDI.PrecioMaximo)
            precioMin = grafoEntrada.value(subject=restriccion, predicate=ECSDI.PrecioMinimo)
            directivasRestrictivas['PrecioMax'] = precioMax
            directivasRestrictivas['PrecioMin'] = precioMin
    # Llamamos a una funcion que nos retorna un grafo con la información acorde al filtro establecido por el usuario
    resultadoComunicacion = findProductsByFilter(**directivasRestrictivas)
    return resultadoComunicacion

# Función que busca productos en la base de datos acorde a los filtros establecidos con anterioriad
def findProductsByFilter(Nombre=None,PrecioMin=0.0,PrecioMax=sys.float_info.max):
    logger.info("Haciendo resultado de busqueda")
    graph = Graph()
    ontologyFile = open('../data/ProductsDB.owl')
    graph.parse(ontologyFile, format='turtle')

    addAnd = False;
    logger.info("Buscando productos")
    query = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?Producto ?Nombre ?Precio ?Descripcion ?Id ?Peso
    where {
        ?Producto rdf:type default:Producto .
        ?Producto default:Nombre ?Nombre .
        ?Producto default:Precio ?Precio .
        ?Producto default:Descripcion ?Descripcion .
        ?Producto default:Id ?Id .
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

        # Generamos el grafo de los filtros
        sujetofiltrado = ECSDI['ProductoFiltrado' + str(getMessageCount())]
        products_filtro.add((sujetofiltrado, RDF.type, ECSDI.Producto))
        products_filtro.add((sujetofiltrado, ECSDI.Nombre, Literal(product_nombre, datatype=XSD.string)))
        products_filtro.add((sujetofiltrado, ECSDI.Precio, Literal(product_precio, datatype=XSD.float)))
        products_filtro.add((sujetofiltrado, ECSDI.Descripcion, Literal(product_descripcion, datatype=XSD.string)))

    thread = Thread(target=registrarFiltro, args=(products_filtro,))
    thread.start()

    logger.info("Respondiendo peticion de busqueda")
    return products_graph


@app.route("/comm")
def comunicacion():
    """
    Entrypoint de comunicacion
    """
    global dsgraph
    global mss_cnt
    pass


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
    #gr = register_message()

def getMessageCount():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio

    :param gmess:
    :return:
    """

    #logger.info('Nos registramos')

    #gr = registerAgent(Buscadoragent, DirectoryAgent, Buscadoragent.uri, getMessageCount())
    return gr


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=buscadorbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')
