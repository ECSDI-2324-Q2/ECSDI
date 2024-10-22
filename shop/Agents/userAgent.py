# -*- coding: utf-8 -*-
"""

filename: UserAgent

Agente que permite interactuar con el usuario


@author: Marc Mostazo
"""

import argparse
import socket
import sys

import rdflib
from requests import get
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
from rdflib import term


__author__ = 'Marc'

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

listaDeProductos = []

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
    print("Procesando venta")
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

    for producto in listaDeCompra:
        sujetoProducto = producto['Sujeto']
        sujetoProducto2 = str(producto['Sujeto'])
        if 'ProductoExterno' in sujetoProducto2:
            print("This is an external product")
            grafoCompra.add((sujetoProducto, RDF.type, ECSDI.ProductoExterno))
            grafoCompra.add((sujetoProducto, ECSDI.GestionExterna, producto['GestionExterna']))
            grafoCompra.add((sujetoProducto, ECSDI.Tarjeta, producto['Tarjeta']))
        else:
            print("This is not an external product")
            grafoCompra.add((sujetoProducto, RDF.type, ECSDI.Producto))
        
        grafoCompra.add((sujetoProducto,ECSDI.Descripcion,producto['Descripcion']))
        grafoCompra.add((sujetoProducto,ECSDI.Nombre,producto['Nombre']))
        grafoCompra.add((sujetoProducto,ECSDI.Precio,producto['Precio']))
        grafoCompra.add((sujetoProducto,ECSDI.Peso,producto['Peso']))
        grafoCompra.add((sujetoCompra, ECSDI.Contiene, URIRef(sujetoProducto)))

    grafoCompra.add((content,ECSDI.De,URIRef(sujetoCompra)))

    # Pedimos información del agente vendedor
    comerciante = getAgentInfo(agn.ComercianteAgent, DirectoryAgent, UserAgent, getMessageCount())
    
    # Enviamos petición de compra al agente vendedor
    logger.info("Enviando petición de compra")
    respuestaVenta = send_message(
        build_message(grafoCompra, perf=ACL.request, sender=UserAgent.uri, receiver=comerciante.uri,
                    msgcnt=getMessageCount(),
                    content=content), comerciante.address)

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

@app.route("/search", methods=['GET', 'POST']) # type: ignore
def search():
    global listaDeProductos
    if request.method == 'GET':
        return render_template('search.html', products = None)
    elif request.method == 'POST':
        if request.form['submit'] == 'Search':
             return enviarPeticionBusqueda(request)
        elif request.form['submit'] == 'Buy':
            print("Comprando")
            return buy(request)
        
@app.route("/return",methods=['GET', 'POST'])  # type: ignore
def getProductsToReturn():
    global listaDeProductos
    if request.method == 'POST':
        if request.form['return'] == 'submit':
            return verProductosRetorno(request)

        elif request.form['return'] == 'Submit':
            return submitReturn(request)
        

def verProductosRetorno(request):
    global listaDeProductos
    logger.info("Haciendo petición de productos enviados")
    grafoDeContenido = Graph()

    accion = ECSDI["PeticionProductosEnviados" + str(getMessageCount())]
    grafoDeContenido.add((accion, RDF.type, ECSDI.PeticionProductosEnviados))
    tarjeta = request.form['tarjeta']
    grafoDeContenido.add((accion, ECSDI.Tarjeta, Literal(tarjeta, datatype=XSD.int)))

    logger.info("enviando petición de productos enviados a gestor de devoluciones")

    # Pedimos información del Gestor de Devoluciones
    agente = getAgentInfo(agn.GestorDevoluciones, DirectoryAgent, UserAgent, getMessageCount())

    logger.info("Enviando petición de productos enviados")
    # Enviamos petición de productos enviados al agente Gestor de Devoluciones
    grafoBusqueda = send_message(
        build_message(grafoDeContenido, perf=ACL.request, sender=UserAgent.uri, receiver=agente.uri,
                      msgcnt=getMessageCount(),
                      content=accion), agente.address)

    logger.info("Recibido resultado de productos enviados")
    listaDeProductos = []
    posicionDeSujetos = {}
    indice = 0
    
    for s, p, o in grafoBusqueda:
        if s not in posicionDeSujetos:
            posicionDeSujetos[s] = indice
            indice += 1
            listaDeProductos.append({})
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
            elif p == ECSDI.FechaDeEntrega:
                producto["FechaDeEntrega"] = o
            listaDeProductos[posicionDeSujetos[s]] = producto

    # Mostramos la lista de productos enviados
    return render_template('devolucion.html', products=listaDeProductos)

def submitReturn(request):
    global listaDeProductos
    logger.info("Haciendo petición de retorno")
    listaDeDevoluciones = []
    for producto in request.form.getlist("checkbox"):
        listaDeDevoluciones.append(listaDeProductos[int(producto)])

    # ACCION -> Peticion Retorno
    accion = ECSDI["PeticionRetorno" + str(getMessageCount())]
    grafoDeContenido = Graph()
    grafoDeContenido.add((accion, RDF.type, ECSDI.PeticionRetorno))
    direccion = request.form['direccion']
    codigoPostal = int(request.form['codigoPostal'])
    motivo = request.form['motivo']

    # Añadimos los productos a devolver
    for producto in listaDeDevoluciones:
        sujetoProducto = producto['Sujeto']
        grafoDeContenido.add((sujetoProducto, RDF.type, ECSDI.ProductoEnviado))
        grafoDeContenido.add((sujetoProducto, ECSDI.Descripcion, producto['Descripcion']))
        grafoDeContenido.add((sujetoProducto, ECSDI.Nombre, producto['Nombre']))
        grafoDeContenido.add((sujetoProducto, ECSDI.Precio, producto['Precio']))
        grafoDeContenido.add((sujetoProducto, ECSDI.Peso, producto['Peso']))
        grafoDeContenido.add((sujetoProducto, ECSDI.FechaDeEntrega, producto['FechaDeEntrega']))
        grafoDeContenido.add((accion, ECSDI.Auna, URIRef(sujetoProducto)))

    sujetoDireccion = ECSDI['Direccion' + str(getMessageCount())]
    grafoDeContenido.add((sujetoDireccion, RDF.type, ECSDI.Direccion))
    grafoDeContenido.add((sujetoDireccion, ECSDI.Direccion, Literal(direccion, datatype=XSD.string)))
    grafoDeContenido.add((sujetoDireccion, ECSDI.CodigoPostal, Literal(codigoPostal, datatype=XSD.int)))
    grafoDeContenido.add((sujetoDireccion, ECSDI.MotivoDevolucion, Literal(motivo, datatype=XSD.string)))
    grafoDeContenido.add((accion, ECSDI.DireccionadoA, URIRef(sujetoDireccion)))

    # Pedimos informacion del Gestor de Devoluciones
    agente = getAgentInfo(agn.GestorDevoluciones, DirectoryAgent, UserAgent, getMessageCount())

    # Enviamos la peticion de retorno al Gestor de Devoluciones
    logger.info("Enviando petición de retorno")
    grafoBusqueda = send_message(
        build_message(grafoDeContenido, perf=ACL.request, sender=UserAgent.uri, receiver=agente.uri,
                      msgcnt=getMessageCount(),
                      content=accion), agente.address)
    logger.info("Recibido resultado de retorno")

    sujeto = grafoBusqueda.value(predicate=RDF.type, object=ECSDI.DevolucionNoValida)

    if (sujeto, RDF.type, ECSDI.DevolucionNoValida) in grafoBusqueda:
        return render_template('devolucionNoValida.html')
    elif (sujeto, RDF.type, ECSDI.DevolucionValida) in grafoBusqueda:
        return render_template('procesandoDevolucion.html')

def UserAgentbehavior1():
    """
    Un comportamiento del agente

    :return:
    """
    registerAgent(UserAgent, DirectoryAgent, UserAgent.uri, getMessageCount())
    
def enviarPeticionBusqueda(request):
    global listaDeProductos
    logger.info('Haciendo petición de busqueda')
    
    contenido = ECSDI['BuscarProducto' + str(getMessageCount())]
    grafoDeContenido = Graph()
    grafoDeContenido.add((contenido, RDF.type, ECSDI.BuscarProducto))
    nombreProducto = request.form['nombre']
    
    # Añadimos el nombre del producto a buscar
    if nombreProducto:
        nombreSujeto = ECSDI['FiltroPorNombre' + str(getMessageCount())]
        grafoDeContenido.add((nombreSujeto, RDF.type, ECSDI.FiltroPorNombre))
        grafoDeContenido.add((nombreSujeto, ECSDI.Nombre, Literal(nombreProducto, datatype=XSD.string)))
        grafoDeContenido.add((contenido, ECSDI.FiltradoPor, URIRef(nombreSujeto)))
    
    precioMinimo = request.form['minPrecio']
    precioMaximo = request.form['maxPrecio']
    
    #Añaadimos el precio minimo y maximo
    if precioMinimo or precioMaximo:
        
        precioSujeto = ECSDI['FiltroPorPrecio' + str(getMessageCount())]
        grafoDeContenido.add((precioSujeto, RDF.type, ECSDI.FiltroPorPrecio))
        if precioMinimo:
            grafoDeContenido.add((precioSujeto, ECSDI.PrecioMinimo, Literal(precioMinimo)))
        if precioMaximo:
            grafoDeContenido.add((precioSujeto, ECSDI.PrecioMaximo, Literal(precioMaximo)))
        grafoDeContenido.add((contenido, ECSDI.FiltradoPor, URIRef(precioSujeto)))
        
    # Pedimos informacion del agente buscador
    agente = getAgentInfo(agn.BuscadorAgent, DirectoryAgent, UserAgent, getMessageCount())
    
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
            # Add conditions for ProductoExterno properties
            elif p == ECSDI.GestionExterna:
                producto["GestionExterna"] = o
            elif p == ECSDI.Tarjeta:
                producto["Tarjeta"] = o
            listaDeProductos[posicionDeSujetos[s]] = producto
    
    # Mostramos los productos filtrados
    return render_template('search.html', products = listaDeProductos)

if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=UserAgentbehavior1)
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port, debug=False)

    # Esperamos a que acaben los behaviors
    ab1.join()
    logger.info('The End')
