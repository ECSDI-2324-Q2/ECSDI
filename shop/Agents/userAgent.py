# -*- coding: utf-8 -*-
"""
filename: personalAgent

Agente que permite interactuar con el usuario


@author: Marc Mostazo
"""

import argparse
import socket
import sys
sys.path.append('../')
from multiprocessing import Queue, Process
from threading import Thread

from flask import Flask, render_template, request
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
    port = 9081
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
app = Flask(__name__, template_folder='./templates')

# Configuration constants and variables
agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente
PersonalAgent = Agent('personalAgent',
                          agn.PersonalAgent,
                          'http://%s:%d/comm' % (hostname, port),
                          'http://%s:%d/Stop' % (hostname, port))
# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global dsgraph triplestore
dsgraph = Graph()


@app.route("/")
def index():

    return render_template('index.html')

@app.route("/search", methods=['GET', 'POST'])
def search():
    global listaDeProductos
    if request.method == 'GET':
        return render_template('search.html', products = None)
    # elif request.method == 'POST':
    #     if request.form['submit'] == 'Search':
    #         return enviarPeticionBusqueda(request)
    #     elif request.form['submit'] == 'Buy':
    #         return buy(request)

def personalagentbehavior1():
    """
    Un comportamiento del agente

    :return:
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
    reg_obj = agn[PersonalAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, PersonalAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(PersonalAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(PersonalAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.PersonalAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=PersonalAgent.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

    return gr

if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=personalagentbehavior1)
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port, debug=False)

    # Esperamos a que acaben los behaviors
    ab1.join()
    logger.info('The End')
