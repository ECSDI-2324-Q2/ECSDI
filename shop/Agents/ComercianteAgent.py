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
import sys

from requests import get
sys.path.append('../')
from multiprocessing import Queue, Process
from threading import Thread

from flask import Flask, request
from rdflib import BNode, URIRef, XSD, Namespace, Literal

from AgentUtil.ACLMessages import *
from AgentUtil.Agent import Agent
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Logging import config_logger
from AgentUtil.OntoNamespaces import ECSDI
from AgentUtil.OntoNamespaces import ACL, DSO
from rdflib.namespace import RDF, FOAF

__author__ = 'Marc Arnau Miquel'

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
    port = 9003
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
ComercianteAgent = Agent('ComercianteAgent',
                    agn.ComercianteAgent,
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

#función inclremental de numero de mensajes
def getMessageCount():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

def registrarCompra(grafoEntrada):
    logger.info("Registrando la compra")
    ontologyFile = open('../data/ComprasDB')

    grafoCompras = Graph()
    grafoCompras.bind('default', ECSDI)
    grafoCompras.parse(ontologyFile, format='turtle')
    grafoCompras += grafoEntrada

    # Guardem el graf
    grafoCompras.serialize(destination='../data/ComprasDB', format='turtle')
    logger.info("Registro de compra finalizado")

def procesarEnvio(grafo, contenido):
    logger.info("Recibida peticion de envio")
    thread1 = Thread(target=registrarEnvio,args=(grafo,contenido))
    thread1.start()
    thread2 = Thread(target=solicitarEnvio,args=(grafo,contenido))
    thread2.start()

def registrarEnvio(grafo, contenido):
    logger.info("Registrando el envio")

    envio = grafo.value(predicate=RDF.type, object=ECSDI.PeticionEnvio)
    grafo.add((envio, ECSDI.Pagado, Literal(False, datatype=XSD.boolean)))

    prioridad = grafo.value(subject=envio, predicate=ECSDI.Prioridad)
    fecha = datetime.now() + timedelta(days=int(prioridad))
    fecha_datetime = datetime.combine(fecha, datetime.min.time())  # convert date to datetime
    grafo.add((envio, ECSDI.FechaEntrega, Literal(fecha_datetime, datatype=XSD.dateTime)))

    grafoEnvios = Graph()
    grafoEnvios.bind('default', ECSDI)

    with open('../data/EnviosDB') as ontologyFile:
        grafoEnvios.parse(ontologyFile, format='turtle')

    grafoEnvios += grafo

    # Guardem el graf
    grafoEnvios.serialize(destination='../data/EnviosDB', format='turtle')
    logger.info("Registro de envio finalizado")


def solicitarEnvio(grafo,contenido):
    grafoCopia = grafo
    grafoCopia.bind('default', ECSDI)
    direccion = grafo.subjects(object=ECSDI.Direccion)
    codigoPostal = None
    logger.info("Haciendo peticion envio a Centro Logistico")
    for d in direccion:
        codigoPostal = grafo.value(subject=d,predicate=ECSDI.CodigoPostal)
    centroLogisticoAgente = getAgentInfo(agn.CentroLogisticoDirectoryAgent, DirectoryAgent, ComercianteAgent, getMessageCount())
    prioridad = grafo.value(subject=contenido,predicate=ECSDI.Prioridad)

    grafoCopia.remove((contenido,ECSDI.Tarjeta,None))
    grafoCopia.remove((contenido,RDF.type,ECSDI.PeticionEnvio))
    sujeto = ECSDI['PeticionEnvioACentroLogistico' + str(getMessageCount())]
    grafoCopia.add((sujeto, RDF.type, ECSDI.PeticionEnvioACentroLogistico))

    for a, b, c in grafoCopia:
        if a == contenido:
            if b == ECSDI.De: #Compra
                grafoCopia.remove((a, b, c))
                grafoCopia.add((sujeto, ECSDI.EnvioDe, c))
            else:
                grafoCopia.remove((a,b,c))
                grafoCopia.add((sujeto,b,c))

    agentesCL = getCentroLogisticoMasCercano(agn.CentroLogisticoAgent, centroLogisticoAgente, ComercianteAgent, getMessageCount(), int(codigoPostal))

    compra = grafoCopia.value(subject=contenido,predicate=ECSDI.Compra)
    compraSize = len(list(grafoCopia.objects(subject=compra, predicate=ECSDI.Contiene)))
    productosVendidos = 0

    ontologyFile = open('../data/CentrosLogisticosBD.owl')

    productos_centrologistico = Graph()
    productos_centrologistico.bind('default', ECSDI)
    productos_centrologistico.parse(ontologyFile, format='turtle')

    # Define the Producto URI
    producto_uri = URIRef("http://www.owl-ontologies.com/ECSDIstore#Producto")   

    for ag in agentesCL:
        if productosVendidos == compraSize:
            break
        # Get the product IDs related to the CentroLogistico through the ECSDI.Producto predicate
        product_ids_centrologistico = [str(o) for o in productos_centrologistico.objects(subject=URIRef(ag.uri), predicate=producto_uri)]

        prod_vender = []

        for prod in grafoCopia.objects(subject=compra, predicate=ECSDI.Contiene):
            prod_id_str = prod.split('#Producto')[-1]
            if prod_id_str in product_ids_centrologistico:
                prod_vender.append(prod)
                productosVendidos += 1
                grafoCopia.add((sujeto, ECSDI.Envia, Literal(prod_id_str)))
                grafoCopia.remove((compra, ECSDI.Contiene, prod))

        send_message(
                    build_message(grafoCopia, perf=ACL.request, sender=ComercianteAgent.uri, receiver=ag.uri,
                                msgcnt=mss_cnt), ag.address)
                
    logger.info("Enviada peticion envio a Centro Logistico")


# Función que efectua y organiza en threads el proceso de vender
def vender(grafoEntrada, content):
    logger.info("Recibida peticion de compra")

    # Guardar Compra
    Thread(target=registrarCompra, args=(grafoEntrada,)).start()

    agente = getAgentInfo(agn.FinancieroAgent, DirectoryAgent, ComercianteAgent, getMessageCount())

    # Se pide la generacion de la factura
    logger.info("Pidiendo factura")
    grafoEntrada.remove((content, RDF.type, ECSDI.PeticionCompra))
    grafoEntrada.add((content, RDF.type, ECSDI.GenerarFactura))
    grafoFactura = send_message(
        build_message(grafoEntrada, perf=ACL.request, sender=ComercianteAgent.uri, receiver=agente.uri,
                      msgcnt=getMessageCount(),
                      content=content), agente.address)

    precioTotal = next((o for s, p, o in grafoFactura if p == ECSDI.PrecioTotal), None)
    logger.info(f"Precio total de la compra: {precioTotal}")

    suj = grafoEntrada.value(predicate=RDF.type, object=ECSDI.GenerarFactura)
    grafoEntrada.add((suj, ECSDI.PrecioTotal, Literal(precioTotal, datatype=XSD.float)))

    grafoProductoExterno = Graph()
    for s in grafoEntrada.subjects(predicate=RDF.type, object=ECSDI.ProductoExterno):
        if grafoEntrada.value(subject=s, predicate=ECSDI.GestionExterna).toPython() is True:
            # Iterate over all triples with the subject
            for p, o in grafoEntrada.predicate_objects(subject=s):
                # Add the triple to grafoProductoExterno
                grafoProductoExterno.add((s, p, o))
                # Remove the triple from grafoEntrada
                grafoEntrada.remove((s, p, o))
            for compra in grafoEntrada.subjects(predicate=ECSDI.Contiene, object=s):
                grafoEntrada.remove((compra, ECSDI.Contiene, s))

    # Enviar compra
    Thread(target=enviarCompra, args=(grafoEntrada, content)).start()
    
    #Notificar vendedor externo
    Thread(target=notificarVendedorExterno, args=(grafoProductoExterno, content)).start()

    return grafoFactura


def notificarVendedorExterno(grafo, content): 
    sujeto = ECSDI["NotificarVendedorExterno" + str(getMessageCount())]
    grafo.add((sujeto, RDF.type, ECSDI.NotificarVendedorExterno))

    agent = getAgentInfo(agn.GestorExterno, DirectoryAgent, ComercianteAgent, getMessageCount())
    logger.info("Notificando al vendedor externo")
    send_message(
        build_message(grafo, perf=ACL.request, sender=ComercianteAgent.uri, receiver=agent.uri, msgcnt=mss_cnt), 
        agent.address
    )

def enviarCompra(grafoEntrada, content):
    logger.info("Haciendo peticion envio")

    sujeto = ECSDI['PeticionEnvio' + str(getMessageCount())]
    grafoEntrada.add((sujeto, RDF.type, ECSDI.PeticionEnvio))

    triples_to_remove = [(a, b, c) for a, b, c in grafoEntrada if a == content]
    for triple in triples_to_remove:
        grafoEntrada.remove(triple)
        grafoEntrada.add((sujeto, triple[1], triple[2]))

    logger.info("Enviando peticion envio")
    procesarEnvio(grafoEntrada, content)
    logger.info("Enviada peticion envio")

#funcion llamada en /comm
@app.route("/comm")
def communication():
    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(format='xml',data=message)

    messageProperties = get_message_properties(grafoEntrada)

    resultadoComunicacion = Graph()

    if messageProperties is None:
        # Respondemos que no hemos entendido el mensaje
        resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                              sender=ComercianteAgent.uri, msgcnt=getMessageCount())
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
            if accion == ECSDI.PeticionCompra:

                # Eliminar los ACLMessage
                for item in grafoEntrada.subjects(RDF.type, ACL.FipaAclMessage):
                    grafoEntrada.remove((item, None, None))

                logger.info("Procesando peticion de compra")
                resultadoComunicacion =  vender(grafoEntrada, content)

            
    logger.info('Respondemos a la peticion')
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

#funcion llamada al principio de un agente
def ComercianteBehavior(queue):

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    registerAgent(ComercianteAgent, DirectoryAgent, ComercianteAgent.uri, getMessageCount())

#función llamada antes de cerrar el servidor
def tidyUp():
    """
    Previous actions for the agent.
    """

    global queue
    queue.put(0)

    pass

if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    ab1 = Process(target=ComercianteBehavior, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    print('The End')