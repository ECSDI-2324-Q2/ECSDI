"""
.. module:: DirectoryService

DirectoryService
*************

:Description: DirectoryService

 Registra los agentes/servicios activos y reparte la carga de las busquedas mediante
 un round robin

:Authors: bejar
    

:Version: 

:Created on: 06/02/2018 8:20 

"""

from Util import gethostname
import socket
import argparse
from FlaskServer import shutdown_server

from flask import Flask, request, render_template
import time
from random import  sample
from uuid import uuid4
import logging

__author__ = 'bejar'
def obscure(dir):
    """
    Hide real hostnames
    """
    odir = {}
    for d in dir:
        _,_,port = dir[d][1].split(':')
        odir[d] = (f'{uuid4()}-{port}', f'{uuid4()}:{port}', dir[d][2])

    return odir

app = Flask(__name__)

directory = {}
loadbalance = {}
schedule = 'equaljobs'


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
            # parametros del mensaje SEARCH = 'TIPO,N' - Busca N agentes de un tipo
            elif messtype == 'SEARCH':
                param = messparam.split(',')

                if len(param) == 1:
                    sertype = param[0]
                    num = 1
                elif len(param) == 2:
                    sertype, num = param
                    num = int(num)
                else:
                    return 'ERROR: INVALID SEARCH PARAMETERS'
                found = [directory[id][1] for id in directory if directory[id][0] == sertype]
                if len(found) != 0:
                    if len(found) > num:
                        lag = sample(found, num)
                    else:
                        lag = found

                    return 'OK: ' + ','.join(lag)
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
    global directory
    global loadbalance

    return render_template('directory.html', dir=obscure(directory), bal=loadbalance)


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

    print('DS Hostname =', hostaddr)

    # Ponemos en marcha el servidor Flask
    app.run(host=hostname, port=port, debug=False, use_reloader=False)
