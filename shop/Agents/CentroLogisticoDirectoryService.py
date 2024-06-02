# -*- coding: utf-8 -*-
"""
filename: CentroLogisticoDirectoryService

Agente que lleva un registro de otros agentes

Utiliza un registro simple que guarda en un grafo RDF

El registro no es persistente y se mantiene mientras el agente funciona

"""
import argparse
from datetime import datetime, timedelta
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
from rdflib.namespace import FOAF, RDF, RDFS

__author__ = 'Arnau'

# Definimos los parametros de la linea de comandos
parser = argparse.ArgumentParser()
parser.add_argument('--open', help="Define si el servidor est abierto al exterior o no", action='store_true',
                    default=False)
parser.add_argument('--port', type=int, help="Puerto de comunicacion del agente")

# Logging
logger = config_logger(level=1)

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = 9010
else:
    port = args.port

if args.open is None:
    hostname = '0.0.0.0'
else:
    hostname = socket.gethostname()

# Directory Service Graph
dsgraph = Graph()

# Vinculamos todos los espacios de nombre a utilizar
dsgraph.bind('acl', ACL)
dsgraph.bind('rdf', RDF)
dsgraph.bind('rdfs', RDFS)
dsgraph.bind('foaf', FOAF)
dsgraph.bind('dso', DSO)

agn = Namespace("http://www.agentes.org#")
CentroLogisticoDirectoryAgent = Agent('CentroLogisticoDirectoryAgent',
                       agn.CentroLogisticoDirectoryAgent,
                       'http://%s:%d/Register' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)

app = Flask(__name__)
mss_cnt = 0

queue1 = Queue()

#función incremental de numero de mensajes
def getMessageCount():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio

    :return:
    """

    logger.info('Nos registramos')

    registerAgent(CentroLogisticoDirectoryAgent, DirectoryAgent, CentroLogisticoDirectoryAgent.uri, getMessageCount())


@app.route("/Register")
def register():
    """
    Entry point del agente que recibe los mensajes de registro
    La respuesta es enviada al retornar la funcion,
    no hay necesidad de enviar el mensaje explicitamente

    Asumimos una version simplificada del protocolo FIPA-request
    en la que no enviamos el mesaje Agree cuando vamos a responder

    :return:
    """

    def process_register():
        # Si la hay extraemos el nombre del agente (FOAF.Name), el URI del agente
        # su direccion y su tipo

        logger.info('Peticion de registro centro logistico')

        agn_add = gm.value(subject=content, predicate=DSO.Address)
        agn_name = gm.value(subject=content, predicate=FOAF.name)
        agn_uri = gm.value(subject=content, predicate=DSO.Uri)
        agn_type = gm.value(subject=content, predicate=DSO.AgentType)
        agn_cp = gm.value(subject=content,predicate=ECSDI.CodigoPostal)


        # Añadimos la informacion en el grafo de registro vinculandola a la URI
        # del agente y registrandola como tipo FOAF.Agent
        dsgraph.add((agn_uri, RDF.type, FOAF.Agent))
        dsgraph.add((agn_uri, FOAF.name, agn_name))
        dsgraph.add((agn_uri, DSO.Address, agn_add))
        dsgraph.add((agn_uri, DSO.AgentType, agn_type))
        dsgraph.add((agn_uri, ECSDI.CodigoPostal,agn_cp))

        logger.info('Registrado agente: ' + agn_name + ' - tipus:' + agn_type)

        # Generamos un mensaje de respuesta
        return build_message(Graph(),
                             ACL.confirm,
                             sender=CentroLogisticoDirectoryAgent.uri,
                             receiver=agn_uri,
                             msgcnt=mss_cnt)

    def process_search(cp):
        # Asumimos que hay una accion de busqueda que puede tener
        # diferentes parametros en funcion de si se busca un tipo de agente
        # o un agente concreto por URI o nombre
        # Podriamos resolver esto tambien con un query-ref y enviar un objeto de
        # registro con variables y constantes

        # Solo consideramos cuando Search indica el tipo de agente
        # Buscamos una coincidencia exacta
        # Retornamos el primero de la lista de posibilidades

        " Aqui tenim una variable cp que es el codi postal."

        logger.info('Peticion de busqueda')

        rsearch = dsgraph.triples((None, DSO.AgentType, None))

        i = 0
        graph = Graph()
        graph.bind('dso', DSO)
        bag = BNode()
        graph.add((bag, RDF.type, RDF.Bag))

        for a, b, c in rsearch:
            agn_uri2 = a
            agn_add = dsgraph.value(subject=agn_uri2, predicate=DSO.Address)
            agn_name = dsgraph.value(subject=agn_uri2, predicate=FOAF.name)
            agn_cp = abs(int(dsgraph.value(subject=agn_uri2, predicate= ECSDI.CodigoPostal)) - int(cp))

            rsp_obj = agn['Directory-response' + str(i)]
            graph.add((rsp_obj, DSO.Address, agn_add))
            graph.add((rsp_obj, DSO.Uri, agn_uri2))
            graph.add((rsp_obj, FOAF.name, agn_name))
            graph.add((rsp_obj,ECSDI.DiferenciaCodigoPostal,Literal(agn_cp, datatype=XSD.int)))
            graph.add((bag, URIRef(u'http://www.w3.org/1999/02/22-rdf-syntax-ns#_') + str(i), rsp_obj))
            logger.info("Agente encontrado: " + agn_name)
            i += 1

        if rsearch is not None:
            return build_message(graph,
                                 ACL.inform,
                                 sender=CentroLogisticoDirectoryAgent.uri,
                                 msgcnt=mss_cnt,
                                 content=bag)
        else:
            # Si no encontramos nada retornamos un inform sin contenido
            return build_message(Graph(),
                                 ACL.inform,
                                 sender=CentroLogisticoDirectoryAgent.uri,
                                 msgcnt=mss_cnt)

    global dsgraph
    global mss_cnt
    # Extraemos el mensaje y creamos un grafo con él
    message = request.args['content']
    gm = Graph()
    gm.parse(format='xml', data=message)

    msgdic = get_message_properties(gm)

    # Comprobamos que sea un mensaje FIPA ACL
    if not msgdic:
        # Si no es, respondemos que no hemos entendido el mensaje
        gr = build_message(Graph(),
                           ACL['not-understood'],
                           sender=DirectoryAgent.uri,
                           msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        if msgdic['performative'] != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(),
                               ACL['not-understood'],
                               sender=DirectoryAgent.uri,
                               msgcnt=mss_cnt)
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia
            # de registro
            content = msgdic['content']
            # Averiguamos el tipo de la accion
            accion = gm.value(subject=content, predicate=RDF.type)

            # Accion de registro
            if accion == DSO.Register:
                gr = process_register()
            # Accion de busqueda
            elif accion == DSO.Search:
                cp = gm.objects(subject=content, predicate=ECSDI.CodigoPostal)
                codigoPostal = None
                for c in cp:
                    codigoPostal = c
                gr = process_search(codigoPostal)
            # No habia ninguna accion en el mensaje
            else:
                gr = build_message(Graph(),
                                   ACL['not-understood'],
                                   sender=DirectoryAgent.uri,
                                   msgcnt=mss_cnt)
    mss_cnt += 1
    return gr.serialize(format='xml')


@app.route('/Info')
def info():
    """
    Entrada que da informacion sobre el agente a traves de una pagina web
    """
    global dsgraph
    global mss_cnt

    return render_template('info.html', nmess=mss_cnt, graph=dsgraph.serialize(format='turtle'))


@app.route("/Stop")
def stop():
    """
    Entrada que para el agente
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def tidyup():
    """
    Acciones previas a parar el agente

    """


def CentroLogisticoDirectoryBehaviour():

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    register_message()


if __name__ == '__main__':
    # Ponemos en marcha los behaviours como procesos
    ab1 = Process(target=CentroLogisticoDirectoryBehaviour)
    ab1.start()

    # Ponemos en marcha el servidor Flask
    app.run(host=hostname, port=port, debug=False)

    ab1.join()
    logger.info('The End')