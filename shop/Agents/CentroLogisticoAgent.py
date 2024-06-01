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
CentroLogisticoAgent = Agent('CentroLogisticoAgent',
                    agn.CentroLogisticoAgent,
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

def responderPeticionEnvio(grafoEntrada, content):
    logger.info("Recibida peticion envio a centro logistico")
    prioritat = grafoEntrada.value(subject=content, predicate=ECSDI.Prioridad)
    
    relacion = grafoEntrada.value(subject=content, predicate=ECSDI.EnvioDe)
    direccion = grafoEntrada.value(subject=relacion, predicate=ECSDI.Destino)
    direccion1 = grafoEntrada.value(subject=direccion, predicate=ECSDI.Direccion)
    codigoPostal = grafoEntrada.value(subject=direccion, predicate=ECSDI.CodigoPostal)
    
    logger.info("Haviendo respuesta a la peticion de envio desde centro logistico")
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
    grafoFaltan.add((direccion, ECSDI.Direccion, Literal(direccion1, datatype=XSD.string)))
    grafoFaltan.add((direccion, ECSDI.CodigoPostal, Literal(codigoPostal, datatype=XSD.int)))
    
    graph = Graph()
    ontolologyFile = open('../data/ProductosCL1')
    graph.parse(ontolologyFile, format='turtle')
    logger.info("Registrando productos pendientes")
    ontolologyFile = open('../data/ProductosPendientesCL1')
    grafoPendientes = Graph()
    grafoPendientes.parse(ontolologyFile, format='turtle')
    
    grafoEnviar = Graph()
    grafoEnviar.bind('default', ECSDI)
    
    for producto in grafoEntrada.objects(subject=relacion, predicate=ECSDI.Contiene):
        nombreP = grafoEntrada.value(subject=producto, predicate=ECSDI.Nombre)
        print("Comprobando si hay " + nombreP)
        query = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                            PREFIX owl: <http://www.w3.org/2002/07/owl#>
                            PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
                            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                            SELECT ?Stock ?Producto ?Nombre ?Descripcion ?Precio ?Peso
                            where {
                                ?Stock rdf:type default:Stock .
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
        
        for product in graph_query:
            logger.info("Hay " + nombreP)
            producto = product.Producto
            descripcion = product.Descripcion
            nombre = product.Nombre
            peso = product.Peso
            precio = product.Precio
            
            logger.info("Añadiendo " + nombreP + " a productos pendientes")
            contentEnviar = ECSDI['ProductoPendiente' + str(getMessageCount())]
            grafoEnviar.add((contentEnviar, RDF.type, ECSDI.ProductoPendiente))
            grafoEnviar.add((contentEnviar, ECSDI.Nombre, Literal(nombre, datatype=XSD.string)))
            grafoEnviar.add((contentEnviar, ECSDI.Peso, Literal(peso, datatype=XSD.float)))
            grafoEnviar.add((contentEnviar, ECSDI.Prioridad, Literal(prioritat, datatype=XSD.int)))
            
            grafoEnviar.add((direccion, ECSDI.Tiene, ECSDI.Direccion))
            grafoEnviar.add((direccion, ECSDI.Direccion, Literal(direccion1, datatype=XSD.string)))
            grafoEnviar.add((direccion, ECSDI.CodigoPostal, Literal(codigoPostal, datatype=XSD.int)))
            grafoEnviar.add((contentEnviar, ECSDI.EnviarA, URIRef(direccion)))
        
        if len(graph_query) == 0:
            logger.info("No hay " + nombreP)
            logger.info("Añadimos " + nombreP + " a la resupuesta a envio desde centro logistico")
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
    
    logger.info("Comprobación existencia de productos finalizada")
    grafoPendientes += grafoEnviar
    grafoPendientes.serialize(destination='../Data/ProductosPendientesCL1', format='turtle')
    logger.info("Registro de productos pendientes finalizado")
    
    return grafoFaltan

#funcion llamada en /comm
@app.route("/comm")
def communication():
    """
    Comunication Entrypoint
    """
    
    global dsGraph
    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message, format='xml')
    
    messageProperties = get_message_properties(grafoEntrada)
    res = Graph()
    
    if messageProperties is None:
        res = build_message(Graph(), ACL['not-understood'], sender=CentroLogisticoAgent.uri, msgcnt=getMessageCount())
    else:
        if messageProperties['performative'] != ACL.request:
            res = build_message(Graph(), ACL['not-understood'], sender=CentroLogisticoAgent.uri, msgcnt=getMessageCount())
        else:
            content = messageProperties['content']
            action = grafoEntrada.value(subject=content, predicate=RDF.type)
            
            if action == ECSDI.PeticionEnvioACentroLogistico:
                for item in grafoEntrada.subjects(RDF.type, ACL.FipaAclMessage):
                    grafoEntrada.remove((item, None, None))
                
                res = responderPeticionEnvio(grafoEntrada, content)
    
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
    Previous actions for the agent
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
    gr = registerAgent(CentroLogisticoAgent, DirectoryAgent, CentroLogisticoAgent.uri, getMessageCount())
    return gr

def CentroLogisticoBehavior(queue):

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    gr = register_message()

if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    ab1 = Process(target=CentroLogisticoBehavior, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    print('The End')