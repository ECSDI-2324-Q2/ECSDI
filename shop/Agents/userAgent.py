# -*- coding: utf-8 -*-
"""
filename: UserAgent

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
UserAgent = Agent('UserAgent',
                          agn.UserAgent,
                          'http://%s:%d/comm' % (hostname, port),
                          'http://%s:%d/Stop' % (hostname, port))
# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

BuscadorAgent = Agent('BuscadorAgent',
                       agn.BuscadorAgent,
                       'http://%s:%d/comm' % (dhostname, 9002),
                       'http://%s:%d/Stop' % (dhostname, 9002))

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
    elif request.method == 'POST':
        if request.form['submit'] == 'Search':
             return enviarPeticionBusqueda(request)
    #     elif request.form['submit'] == 'Buy':
    #         return buy(request)

def UserAgentbehavior1():
    """
    Un comportamiento del agente

    :return:
    """
    gr = register_message()
    
def getMessageCount():
    global mss_cnt
    if mss_cnt is None:
        mss_cnt = 0
    mss_cnt += 1
    return mss_cnt

def enviarPeticionBusqueda(request):
    global listaProductos
    logger.info('Haciendo petición de busqueda')
    
    contenido = ECSDI['BuscarProducto' + str(getMessageCount())]
    grafoDeContenido = Graph()
    grafoDeContenido.add((contenido, RDF.type, ECSDI.BuscarProducto))
    nombreProducto = request.form['nombre']
    
    # Añadimos el nombre del producto a buscar
    if nombreProducto:
        print(nombreProducto)
        nombreSujeto = ECSDI['FiltroPorNombre' + str(getMessageCount())]
        grafoDeContenido.add((nombreSujeto, RDF.type, ECSDI.FiltroPorNombre))
        grafoDeContenido.add((nombreSujeto, ECSDI.Nombre, Literal(nombreProducto, datatype=XSD.string)))
        grafoDeContenido.add((contenido, ECSDI.FiltradoPor, URIRef(nombreSujeto)))
    
    precioMinimo = request.form['minPrecio']
    precioMaximo = request.form['maxPrecio']
    
    #Añaadimos el precio minimo y maximo
    if precioMinimo or precioMaximo:
        print(precioMinimo)
        print(precioMaximo)
        
        precioSujeto = ECSDI['FiltroPorPrecio' + str(getMessageCount())]
        grafoDeContenido.add((precioSujeto, RDF.type, ECSDI.FiltroPorPrecio))
        if precioMinimo:
            grafoDeContenido.add((precioSujeto, ECSDI.PrecioMinimo, Literal(precioMinimo)))
        if precioMaximo:
            grafoDeContenido.add((precioSujeto, ECSDI.PrecioMaximo, Literal(precioMaximo)))
        grafoDeContenido.add((contenido, ECSDI.FiltradoPor, URIRef(precioSujeto)))
        
    # Pedimos informacion del agente buscador
    agente = BuscadorAgent
    
    # Enviamos peticion de busqueda al agente buscador
    logger.info('Enviando peticion de busqueda')
    grafoBusqueda = send_message(
        build_message(grafoDeContenido, perf=ACL.request, sender=UserAgent.uri, receiver=agente.uri, msgcnt=getMessageCount(), content=contenido),
        agente.address
    )
    
    logger.info('Recibiendo respuesta de la busqueda')
    listaDeProductos = []
    posicionDeSujetos = {}
    indice = 0
    
    sujetos = grafoBusqueda.objects(predicate=ECSDI.Muestra)
    for sujeto in sujetos:
        posicionDeSujetos[sujeto] = indice
        indice += 1
        listaDeProductos.append({})
    
    for s, p, o in grafoBusqueda:
        if s in posicionDeSujetos:
            producto = listaDeProductos[posicionDeSujetos[s]]
            if p == ECSDI.Nombre:
                producto["Nombre"] = o
            elif p == ECSDI.Precio:
                producto["Precio"] = o
            elif p == ECSDI.Descripcion:
                producto["Descripcion"] = o
            elif p == ECSDI.Id:
                producto["Id"] = o
            elif p == ECSDI.Peso:
                producto["Peso"] = o
            elif p == RDF.type:
                producto["Sujeto"] = s
            listaDeProductos[posicionDeSujetos[s]] = producto
    
    # Mostramos los productos filtrados
    return render_template('search.html', products = listaDeProductos)
    
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
    reg_obj = agn[UserAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, UserAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(UserAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(UserAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.UserAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=UserAgent.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

    return gr

if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=UserAgentbehavior1)
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port, debug=False)

    # Esperamos a que acaben los behaviors
    ab1.join()
    logger.info('The End')
