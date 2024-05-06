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

# Función que lleva y devuelve la cuenta de mensajes
def getMessageCount():
    global mss_cnt
    if mss_cnt is None:
        mss_cnt = 0
    mss_cnt += 1
    return mss_cnt


# Función que procesa una venta y la envía el grafo resultado de haber hablado con el agente correspondiente
def procesarVenta(listaDeCompra, prioridad, numTarjeta, direccion, codigoPostal):
    #Creamos la compra
    grafoCompra = Graph()

    # ACCION -> PeticionCompra
    content = ECSDI['PeticionCompra' + str(getMessageCount())]
    grafoCompra.add((content,RDF.type,ECSDI.PeticionCompra))
    grafoCompra.add((content,ECSDI.Prioridad,Literal(prioridad, datatype=XSD.int)))
    grafoCompra.add((content,ECSDI.Tarjeta,Literal(numTarjeta, datatype=XSD.int)))

    sujetoDireccion = ECSDI['Direccion'+ str(getMessageCount())]
    grafoCompra.add((sujetoDireccion,RDF.type,ECSDI.Direccion))
    grafoCompra.add((sujetoDireccion,ECSDI.Direccion,Literal(direccion,datatype=XSD.string)))
    grafoCompra.add((sujetoDireccion,ECSDI.CodigoPostal,Literal(codigoPostal,datatype=XSD.int)))

    sujetoCompra = ECSDI['Compra'+str(getMessageCount())]
    grafoCompra.add((sujetoCompra, RDF.type, ECSDI.Compra))
    grafoCompra.add((sujetoCompra, ECSDI.Destino, URIRef(sujetoDireccion)))

    # Añadimos los productos
    for producto in listaDeCompra:
        sujetoProducto = producto['Sujeto']
        grafoCompra.add((sujetoProducto, RDF.type, ECSDI.Producto))
        grafoCompra.add((sujetoProducto,ECSDI.Descripcion,producto['Descripcion']))
        grafoCompra.add((sujetoProducto,ECSDI.Nombre,producto['Nombre']))
        grafoCompra.add((sujetoProducto,ECSDI.Precio,producto['Precio']))
        grafoCompra.add((sujetoProducto,ECSDI.Peso,producto['Peso']))
        grafoCompra.add((sujetoCompra, ECSDI.Contiene, URIRef(sujetoProducto)))

    grafoCompra.add((content,ECSDI.De,URIRef(sujetoCompra)))
    print(grafoCompra.serialize(format='xml'))

    # # Pedimos información del agente vendedor
    # vendedor = getAgentInfo(agn.VendedorAgent, DirectoryAgent, UserPersonalAgent,getMessageCount())

    # # Enviamos petición de compra al agente vendedor
    # logger.info("Enviando petición de compra")
    # respuestaVenta = send_message(
    #     build_message(grafoCompra, perf=ACL.request, sender=UserPersonalAgent.uri, receiver=vendedor.uri,
    #                   msgcnt=getMessageCount(),
    #                   content=content), vendedor.address)

    # logger.info("Recibido resultado de compra")
    return respuestaVenta

# Función que renderiza los productos comprados
def buy(request):
    global listaDeProductos
    logger.info("Haciendo petición de compra")
    listaDeCompra = []
    for producto in request.form.getlist("checkbox"):
        listaDeCompra.append(listaDeProductos[int(producto)])

    numTarjeta = int(request.form['numeroTarjeta'])
    prioridad = int(request.form['prioridad'])
    direccion = request.form['direccion']
    codigoPostal = int(request.form['codigoPostal'])
    respuestaVenta = procesarVenta(listaDeCompra, prioridad, numTarjeta, direccion, codigoPostal)
    factura = respuestaVenta.value(predicate=RDF.type, object=ECSDI.Factura)
    tarjeta = respuestaVenta.value(subject=factura, predicate=ECSDI.Tarjeta)
    total = respuestaVenta.value(subject=factura, predicate=ECSDI.PrecioTotal)
    productos = respuestaVenta.subjects(object=ECSDI.Producto)
    productosEnFactura = []
    for producto in productos:
        product = [respuestaVenta.value(subject=producto, predicate=ECSDI.Nombre),
                   respuestaVenta.value(subject=producto, predicate=ECSDI.Precio)]
        productosEnFactura.append(product)

    # Mostramos la factura
    return render_template('venta.html', products=productosEnFactura, tarjeta=tarjeta, total=total)


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
