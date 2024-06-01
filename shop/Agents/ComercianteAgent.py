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
    #thread2 = Thread(target=solicitarEnvio,args=(grafo,contenido))
    #thread2.start()

def registrarEnvio(grafo, contenido):

    envio = grafo.value(predicate=RDF.type,object=ECSDI.PeticionEnvio)

    grafo.add((envio,ECSDI.Pagado,Literal(False,datatype=XSD.boolean)))
    prioridad = grafo.value(subject=envio, predicate=ECSDI.Prioridad)
    fecha = datetime.now() + timedelta(days=int(prioridad))
    grafo.add((envio,ECSDI.FechaEntrega,Literal(fecha, datatype=XSD.date)))
    logger.info("Registrando el envio")
    ontologyFile = open('../data/EnviosDB')

    grafoEnvios = Graph()
    grafoEnvios.bind('default', ECSDI)
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
    # solicitamos centros logisticos dependiendo del codigo postal
    if codigoPostal is not None:
        agentes = getCentroLogisticoMasCercano(agn.CentroLogisticoAgent, centroLogisticoAgente, ComercianteAgent, getMessageCount(), int(codigoPostal))


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

        for ag in agentes:
            logger.info("Enviando peticion envio a Centro Logistico")
            respuesta = send_message(
                build_message(grafoCopia, perf=ACL.request, sender=ComercianteAgent.uri, receiver=ag.uri,
                              msgcnt=getMessageCount(),
                              content=sujeto), ag.address)
            logger.info("Recibida respuesta de envio a Centro Logistico")
            accion = respuesta.subjects(predicate=RDF.type, object=ECSDI.RespuestaEnvioDesdeCentroLogistico)
            contenido = None
            for a in accion:
                contenido = a

            for item in respuesta.subjects(RDF.type, ACL.FipaAclMessage):
                respuesta.remove((item, None, None))
            respuesta.remove((None, RDF.type, ECSDI.RespuestaEnvioDesdeCentroLogistico))
            respuesta.add((sujeto, RDF.type, ECSDI.PeticionEnvioACentroLogistico))

            grafoCopia = respuesta

            contiene = False
            for a, b, c in grafoCopia:
                if a == contenido:
                    if b == ECSDI.Faltan:  # Compra
                        grafoCopia.remove((a, b, c))
                        grafoCopia.add((sujeto, ECSDI.EnvioDe, c))

                    elif b == ECSDI.Contiene:
                        contiene = True
                    else:
                        grafoCopia.remove((a, b, c))
                        grafoCopia.add((sujeto, b, c))

            if not contiene:
                break
            else:
                logger.info("Faltan productos por enviar. Probamos con otro centro logístico")
    logger.info("Enviada peticion envio a Centro Logistico")


# Función que efectua y organiza en threads el proceso de vender
def vender(grafoEntrada, content):
    logger.info("Recibida peticion de compra")
    # Guardar Compra
    thread = Thread(target=registrarCompra, args=(grafoEntrada,))
    thread.start()

    agente = getAgentInfo(agn.FinancieroAgent, DirectoryAgent, ComercianteAgent, getMessageCount())

    # Se pide la generacion de la factura
    logger.info("Pidiendo factura")
    grafoEntrada.remove((content, RDF.type, ECSDI.PeticionCompra))
    grafoEntrada.add((content, RDF.type, ECSDI.GenerarFactura))
    grafoFactura = send_message(
        build_message(grafoEntrada, perf=ACL.request, sender=ComercianteAgent.uri, receiver=agente.uri,
                    msgcnt=getMessageCount(),
                    content=content), agente.address)

    for s, p, o in grafoFactura:
    # If the predicate is ECSDI.PrecioTotal, extract the object as the precioTotal
        if p == ECSDI.PrecioTotal:
            precioTotal = o
            break

    logger.info("Precio total de la compra: " + str(precioTotal))
    suj = grafoEntrada.value(predicate=RDF.type, object=ECSDI.GenerarFactura)
    grafoEntrada.add((suj, ECSDI.PrecioTotal, Literal(precioTotal, datatype=XSD.float)))

    # # Enviar compra
    thread = Thread(target=enviarCompra, args=(grafoEntrada, content))
    thread.start()
    solicitarEnvio(grafoEntrada, content)

    logger.info("Devolviendo factura")
    return grafoFactura

def enviarCompra(grafoEntrada,content):
    # Enviar mensaje con la compra a enviador
    logger.info("Haciendo peticion envio")
    grafoEntrada.remove((content, RDF.type, ECSDI.GenerarFactura))
    sujeto = ECSDI['PeticionEnvio' + str(getMessageCount())]
    grafoEntrada.add((sujeto, RDF.type, ECSDI.PeticionEnvio))

    for a, b, c in grafoEntrada:
        if a == content:
            grafoEntrada.remove((a, b, c))
            grafoEntrada.add((sujeto, b, c))
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