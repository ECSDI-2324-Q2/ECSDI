"""
.. module:: DirectoryService

DirectoryService
*************

:Description: DirectoryService

 Registra los agentes/servicios activos y reparte la carga de las busquedas mediante
 un round robin

:Authors: Marc
    

:Version: 

:Created on: 06/02/2018 8:20 

"""
import sys

from rdflib import Graph, RDF, RDFS, FOAF, Namespace
sys.path.append('../')
from AgentUtil.Util import gethostname
import socket
import argparse
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, get_message_properties

from flask import Flask, request, render_template
import numpy as np
import time
from random import randint
from uuid import uuid4
import logging
from AgentUtil.OntoNamespaces import ACL, DSO
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger

__author__ = 'ECSDIShop'

def obscure(dir):
    """
    Hide real hostnames
    """
    odir = {}
    for d in dir:
        _,_,port = dir[d][1].split(':')
        odir[d] = (dir[d][0], f'{uuid4()}:{port}', dir[d][2])

    return odir


__author__ = 'ECSDIstore'

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
    port = 9000
else:
    port = args.port

if args.open is None:
    hostname = '0.0.0.0'
else:
    hostname = socket.gethostname()


app = Flask(__name__)
mss_cnt = 0

directory = {}
loadbalance = {}
schedule = 'equaljobs'

# Directory Service Graph
dsgraph = Graph()

# Vinculamos todos los espacios de nombre a utilizar
dsgraph.bind('acl', ACL)
dsgraph.bind('rdf', RDF)
dsgraph.bind('rdfs', RDFS)
dsgraph.bind('foaf', FOAF)
dsgraph.bind('dso', DSO)

agn = Namespace("http://www.agentes.org#")
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))



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

        logger.info('Peticion de registro')

        agn_add = gm.value(subject=content, predicate=DSO.Address)
        agn_name = gm.value(subject=content, predicate=FOAF.name)
        agn_uri = gm.value(subject=content, predicate=DSO.Uri)
        agn_type = gm.value(subject=content, predicate=DSO.AgentType)

        # Añadimos la informacion en el grafo de registro vinculandola a la URI
        # del agente y registrandola como tipo FOAF.Agent
        dsgraph.add((agn_uri, RDF.type, FOAF.Agent))
        dsgraph.add((agn_uri, FOAF.name, agn_name))
        dsgraph.add((agn_uri, DSO.Address, agn_add))
        dsgraph.add((agn_uri, DSO.AgentType, agn_type))

        logger.info('Registrado agente: ' + agn_name)


        # Generamos un mensaje de respuesta
        return build_message(Graph(),
                             ACL.confirm,
                             sender=DirectoryAgent.uri,
                             receiver=agn_uri,
                             msgcnt=mss_cnt)
    
    def process_search():
        # Asumimos que hay una accion de busqueda que puede tener
        # diferentes parametros en funcion de si se busca un tipo de agente
        # o un agente concreto por URI o nombre
        # Podriamos resolver esto tambien con un query-ref y enviar un objeto de
        # registro con variables y constantes

        # Solo consideramos cuando Search indica el tipo de agente
        # Buscamos una coincidencia exacta
        # Retornamos el primero de la lista de posibilidades

        logger.info('Peticion de busqueda')

        agn_type = gm.value(subject=content, predicate=DSO.AgentType)
        rsearch = dsgraph.triples((None, DSO.AgentType, agn_type))

        if rsearch is not None:
            agn_uri = list(rsearch)[0][0]
            agn_add = dsgraph.value(subject=agn_uri, predicate=DSO.Address)
            gr = Graph()
            gr.bind('dso', DSO)
            rsp_obj = agn['Directory-response']
            gr.add((rsp_obj, DSO.Address, agn_add))
            gr.add((rsp_obj, DSO.Uri, agn_uri))
            return build_message(gr,
                                 ACL.inform,
                                 sender=DirectoryAgent.uri,
                                 msgcnt=mss_cnt,
                                 receiver=agn_uri,
                                 content=rsp_obj)
        else:
            # Si no encontramos nada retornamos un inform sin contenido
            return build_message(Graph(),
                                 ACL.inform,
                                 sender=DirectoryAgent.uri,
                                 msgcnt=mss_cnt)
    
    global dsgraph
    global mss_cnt
    # Extraemos el mensaje y creamos un grafo con él
    message = request.args['content']
    gm = Graph()
    gm.parse(format='xml',data=message)

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
            elif accion == DSO.Search:
                gr = process_search()
            # No habia ninguna accion en el mensaje
            else:
                gr = build_message(Graph(),
                                   ACL['not-understood'],
                                   sender=DirectoryAgent.uri,
                                   msgcnt=mss_cnt)
    mss_cnt += 1
    return gr.serialize(format='xml')

@app.route("/message")
def message():
    """
    Entrypoint para todas las comunicaciones

    :return:
    """
    global directory
    global loadbalance

    mess = request.args['message']


    if '|' not in mess:
        return 'ERROR: INVALID MESSAGE'
    else:
        # Sintaxis de los mensajes "TIPO|PARAMETROS"
        messtype, messparam = mess.split('|')

        if messtype not in ['REGISTER', 'SEARCH', 'UNREGISTER']:
            return 'ERROR: NO SUCH ACTION'
        else:
            # parametros mensaje REGISTER = "ID,TIPO,ADDRESS"
            if messtype == 'REGISTER':
                param = messparam.split(',')
                if len(param) == 3:
                    serid, sertype, seraddress = param
                    if serid not in directory:
                        directory[serid] = (sertype, seraddress, time.strftime('%Y-%m-%d %H:%M'))
                        loadbalance[serid] = 0
                        return 'OK: REGISTER SUCCESS'
                    else:
                        return 'ERROR: ID ALREADY REGISTERED'
                else:
                    return 'ERROR: REGISTER INVALID PARAMETERS'
            # parametros del mensaje SEARCH = 'TIPO'
            elif messtype == 'SEARCH':
                sertype = messparam
                found = [(id, directory[id][1]) for id in directory if directory[id][0] == sertype]
                if len(found) != 0:
                    if schedule == 'equaljobs':
                        # balanceo por igual numero de jobs
                        bal = [loadbalance[id] for id, _ in found]
                        pos = np.argmin(bal)
                    elif schedule == 'random':
                        pos = randint(0, len(found) - 1)
                    else:
                        pos = 0
                    loadbalance[found[pos][0]] += 1
                    return 'OK: ' + found[pos][1]
                else:
                    return 'ERROR: NOT FOUND'
            # parametros del mensaje UNREGISTER = 'ID'
            elif messtype == 'UNREGISTER':
                serid = messparam
                if serid in directory:
                    del directory[serid]
                    return 'OK: UNREGISTER SUCCESS'
                else:
                    return 'ERROR: NOT REGISTERED'


@app.route('/info')
def info():
    """
    Entrada que da informacion sobre el agente a traves de una pagina web
    """
    global dsgraph
    global mss_cnt

    return render_template('info.html', nmess=mss_cnt, graph=dsgraph.serialize(format='turtle'))


@app.route("/stop")
def stop():
    """
    Entrada que para el agente
    """
    shutdown_server()
    return "Parando Servidor"


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--open', help="Define si el servidor esta abierto al exterior o no", action='store_true',
                        default=False)
    parser.add_argument('--verbose', help="Genera un log de la comunicacion del servidor web", action='store_true',
                        default=False)
    parser.add_argument('--port', type=int, help="Puerto de comunicacion del agente")
    parser.add_argument('--schedule', default='random', choices=['equaljobs', 'random'],
                        help="Algoritmo de reparto de carga")

    # parsing de los parametros de la linea de comandos
    args = parser.parse_args()

    if not args.verbose:
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

    # Configuration stuff
    if args.port is None:
        port = 9000
    else:
        port = args.port

    if args.open:
        hostname = '0.0.0.0'
        hostaddr = gethostname()
    else:
        hostaddr = hostname = socket.gethostname()

    schedule = args.schedule

    print('DS Hostname =', hostaddr)
    # Ponemos en marcha el servidor Flask
    app.run(host=hostname, port=port, debug=False, use_reloader=False)
