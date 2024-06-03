# -*- coding: utf-8 -*-

"""
Agente usando los servicios web de Flask
/comm es la entrada para la recepcion de mensajes del agente
/Stop es la entrada que para el agente
Tiene una funcion AgentBehavior1 que se lanza como un thread concurrente
Asume que el agente de registro esta en el puerto 9000
"""
import argparse
import re
import socket
import sys
from datetime import datetime
from datetime import timedelta
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
GestorDevolucionesAgent = Agent('GestorDevolucionesAgent',
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

def validarDevolucion(content, grafoEntrada):
    motivo = next(grafoEntrada.objects(predicate=ECSDI.MotivoDevolucion), None)
    logger.info("Recibida peticion de retorno con motivo: " + motivo)
    motivo = str(motivo)
    if motivo == "noSatisface":
        products = grafoEntrada.objects(subject=content, predicate= ECSDI.Auna)

        limit = datetime.now() - timedelta(days=15)

        for product in products:
            fecha = grafoEntrada.value(subject=product, predicate=ECSDI.FechaDeEntrega)
            fecha = datetime.strptime(str(fecha), '%Y-%m-%dT%H:%M:%S')

            if fecha >= limit:
                print(f"Product {product} is within 15 days.")
            else:
                return False
    return True
    

# Función encargada del retorno de productos distribuyendo el trabajo en diversos threads
def retornarProductos(content, grafoEntrada):
    result = Graph()
    sujeto = ECSDI['PeticionDevolucion' + str(getMessageCount())]
    
    if not validarDevolucion(content, grafoEntrada):
        logger.error("Devolucion no valida")
        result.add((sujeto, RDF.type, ECSDI.DevolucionNoValida))
        return result
    
    direccionRetorno = next(grafoEntrada.objects(predicate=ECSDI.Direccion), None)
    codigoPostal = next(grafoEntrada.objects(predicate=ECSDI.CodigoPostal), None)
    
    Thread(target=solicitarRecogida, args=(direccionRetorno, codigoPostal)).start()
    Thread(target=borrarProductosRetornados, args=(grafoEntrada, content)).start()
    
    logger.info("Respondiendo peticion de retorno")
    result.add((sujeto, RDF.type, ECSDI.DevolucionValida))
    return result

# Función que atiende la petición de retorno de todos los productos enviados por un usuario con una tarjeta
def solicitarProductosEnviados(content, grafoEntrada):
    logger.info("Recibida peticion de productos enviados")
    
    tarjeta = next(grafoEntrada.objects(subject=content, predicate=ECSDI.Tarjeta), None)
    if tarjeta is None:
        logger.error("Tarjeta not found in the input graph")
        return Graph()
    
    graph = Graph()
    with open('../data/EnviosDB') as ontologyFile:
        graph.parse(ontologyFile, format='turtle')
    
    logger.info(f"Buscamos productos comprados por {tarjeta}")
    
    query = f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?PeticionEnvio ?Producto ?Nombre ?Precio ?Descripcion ?Peso ?Tarjeta ?Compra ?FechaEntrega
        where {{
            ?PeticionEnvio rdf:type default:PeticionEnvio .
            ?PeticionEnvio default:Tarjeta ?Tarjeta .
            ?PeticionEnvio default:De ?Compra .
            ?PeticionEnvio default:FechaEntrega ?FechaEntrega .
            ?Compra default:Contiene ?Producto .       
            ?Producto default:Nombre ?Nombre .
            ?Producto default:Precio ?Precio .
            ?Producto default:Descripcion ?Descripcion .
            ?Producto default:Peso ?Peso .
            FILTER(?Tarjeta = {tarjeta})
        }}
        """
    resultadoConsulta = graph.query(query)
    resultadoComunicacion = Graph()

    # Añadimos los productos enviados que coincidan
    for product in resultadoConsulta:
        sujeto = ECSDI['ProductoEnviado' + str(getMessageCount())]
        resultadoComunicacion.add((sujeto, RDF.type, ECSDI.ProductoEnviado))
        resultadoComunicacion.add((sujeto, ECSDI.Nombre, Literal(product.Nombre, datatype=XSD.string)))
        resultadoComunicacion.add((sujeto, ECSDI.Precio, Literal(product.Precio, datatype=XSD.float)))
        resultadoComunicacion.add((sujeto, ECSDI.Descripcion, Literal(product.Descripcion, datatype=XSD.string)))
        resultadoComunicacion.add((sujeto, ECSDI.Peso, Literal(product.Peso, datatype=XSD.float)))
        resultadoComunicacion.add((sujeto, ECSDI.FechaDeEntrega, Literal(product.FechaEntrega, datatype=XSD.dateTime)))
    
    logger.info("Respondiendo peticion de devolucion de productos enviados")
    
    return resultadoComunicacion

# Función que elimina productos devueltos de la base de datos
def borrarProductosRetornados(grafo, content):
    logger.info("Registramos la devolucion")
    
    products = grafo.objects(subject=content, predicate= ECSDI.Auna)

    grafoEnvios = Graph()
    grafoEnvios.bind('default', ECSDI)
    
    with open('../data/EnviosDB') as ontologyFile:
        grafoEnvios.parse(ontologyFile, format='turtle')

    for product in products:
        compra = grafo.value(subject=product, predicate=ECSDI.EsDe)
        nombre = grafo.value(subject=product, predicate=ECSDI.Nombre)

        query = f"""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?Producto ?Nombre  
            WHERE {{  
                ?Producto rdf:type default:Producto . 
                ?Producto default:Nombre ?Nombre .
                FILTER(?Nombre = '{nombre}')
            }}
            """

        producto = next((p.Producto for p in grafoEnvios.query(query)), None)
        if producto is not None:
            grafoEnvios.remove((compra, None, producto))

    # Guardem el graf
    grafoEnvios.serialize(destination='../data/EnviosDB', format='turtle')
    logger.info("Registro de devolucion finalizado")

# Función que solicita a un Transportista prefijado la recogida de un conjunto de productos a una dirección determinada
def solicitarRecogida(direccionRetorno, codigoPostal):
    logger.info("Haciendo peticion de recoger devolucion")

    accion = ECSDI["PeticionRecogerDevolucion" + str(getMessageCount())]
    sujetoDireccion = ECSDI['Direccion' + str(getMessageCount())]

    peticion = Graph()
    peticion.add((accion, RDF.type, ECSDI.PeticionRecogerDevolucion))
    peticion.add((sujetoDireccion, RDF.type, ECSDI.Direccion))
    peticion.add((sujetoDireccion, ECSDI.Direccion, Literal(direccionRetorno, datatype=XSD.string)))
    peticion.add((sujetoDireccion, ECSDI.CodigoPostal, Literal(codigoPostal, datatype=XSD.int)))
    peticion.add((accion, ECSDI.Desde, URIRef(sujetoDireccion)))

    agente = getAgentInfo(agn.TransportistaDevolucionesAgent, DirectoryAgent, GestorDevolucionesAgent, getMessageCount())

    logger.info("Enviando peticion de recoger devolucion")
    send_message(
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
    grafoEntrada.parse(data=message, format='xml')

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