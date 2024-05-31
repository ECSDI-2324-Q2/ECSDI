# -*- coding: utf-8 -*-
"""
filename: userPersonalAgent

Agente que interactua con el usuario.
"""
import random

import re
import sys
sys.path.append('../')
from AgentUtil.ACLMessages import getAgentInfo, build_message, send_message, get_message_properties
from AgentUtil.OntoNamespaces import ECSDI
import argparse
import socket
from multiprocessing import Process, Queue
from flask import Flask, render_template, request
from rdflib import Graph, Namespace, RDF, URIRef, Literal, XSD
from AgentUtil.Agent import Agent
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Logging import config_logger
from rdflib.namespace import RDF, FOAF
from AgentUtil.OntoNamespaces import ACL, DSO

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
    port = 9030
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

# Flask stuff
app = Flask(__name__, template_folder='../templates')

# Configuration constants and variables
agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente
VendedorPersonalAgent = Agent('VendedorPersonalAgent',
                          agn.VendedorPersonalAgent,
                          'http://%s:%d/comm' % (hostname, port),
                          'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.DirectoryAgent,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global dsgraph triplestore
dsgraph = Graph()

# Queue
queue = Queue()

# Flask app
app = Flask(__name__)

# Productos encontrados
listaDeProductos = []

# Función que lleva y devuelve la cuenta de mensajes
def getMessageCount():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

# Función que añade un producto externo a la base de datos de la tienda
def addProducto(request):
    logger.info("Añadiendo producto")
    nombreProducto = request.form['nombreProducto']
    tarjeta = request.form['tarjeta']
    descripcion = request.form['descripcionProducto']
    peso = request.form['peso']
    precio = request.form['precio']
    gestionExterna = request.form.get('gestionExterna') is None

    logger.info("Haciendo petición de agregar producto")
    sujeto = ECSDI["PeticionAgregarProducto" + str(getMessageCount())]
    graph = Graph()
    graph.add((sujeto, RDF.type, ECSDI.PeticionAgregarProducto))
    graph.add((sujeto, ECSDI.Nombre, Literal(nombreProducto, datatype=XSD.string)))
    graph.add((sujeto, ECSDI.Precio, Literal(precio, datatype=XSD.float)))
    graph.add((sujeto, ECSDI.Descripcion, Literal(descripcion, datatype=XSD.string)))
    graph.add((sujeto, ECSDI.Tarjeta, Literal(tarjeta, datatype=XSD.string)))
    graph.add((sujeto, ECSDI.GestionExterna, Literal(gestionExterna, datatype=XSD.boolean)))
    graph.add((sujeto, ECSDI.Peso, Literal(peso, datatype=XSD.float)))
    # Obtenemos la información del gestor externo
    agente = getAgentInfo(agn.GestorExterno, DirectoryAgent, VendedorPersonalAgent, getMessageCount())
    # Enviamos petición de agregar producto al gestor externo
    logger.info("Enviando petición de agregar producto")
    respuesta = send_message(
        build_message(graph, perf=ACL.request, sender=VendedorPersonalAgent.uri, receiver=agente.uri,
                      msgcnt=getMessageCount(),
                      content=sujeto), agente.address)
    logger.info("Enviada petición de agregar producto")
    return render_template('procesandoArticulo.html')

# Función que devuelve la página principal de ECSDIstore
@app.route("/", methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return render_template('vendedorExternoIndex.html')
    else:
        if request.form['submit'] == 'Submit':
            return addProducto(request)

# Funcion para la comunicación
@app.route("/comm")
def comunicacion():
    """
    Entrypoint de comunicacion del agente
    """
    return "Ruta de comunicación"

@app.route("/Stop")
def stop():
    """
    Entrypoint to the agent
    :return: string
    """
    shutdown_server()
    return "Stopping server"

def VendedorPersonalAgentBehavior(queue):

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
    reg_obj = agn[VendedorPersonalAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, VendedorPersonalAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(VendedorPersonalAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(VendedorPersonalAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.VendedorPersonalAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=VendedorPersonalAgent.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

    return gr

if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    ab1 = Process(target=VendedorPersonalAgentBehavior, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    print('The End')