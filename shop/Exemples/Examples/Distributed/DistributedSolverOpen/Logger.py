"""
.. module:: Logger

Logger
*************

:Description: Logger

    Registra y genera una grafica de los problemas resueltos y quien los ha resuelto

:Authors: bejar
    

:Version: 

:Created on: 06/02/2018 8:21 

"""

from io import BytesIO
from Util import gethostname
import socket
import argparse
from FlaskServer import shutdown_server
import requests
from requests import ConnectionError
from flask import Flask, request, render_template
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import base64
import numpy as np
import time
import logging
from uuid import uuid4

__author__ = 'bejar'

app = Flask(__name__)

workers_logging = {}


@app.route("/message")
def message():
    """
    Entrypoint para todas las comunicaciones

    :return:
    """
    global workers_logging

    mess = request.args['message']

    if ',' in mess and len(mess.split(',')) == 2:
        id, prob = mess.split(',')
        if id in workers_logging:
            if prob in workers_logging[id]:
                workers_logging[id][prob] += 1
            else:
                workers_logging[id][prob] = 1
        else:
            workers_logging[id] = {prob: 1}
    return 'OK'


@app.route('/info')
def info():
    """
    Entrada que da informacion sobre el agente a traves de una pagina web
    """
    global workers_logging

    types = set()
    solvers = workers_logging.keys()
    for solv in workers_logging:
        for tp in workers_logging[solv]:
            types.add(tp)

    lbars = []
    for t in types:
        bar = []
        for solv in workers_logging:
            if t in workers_logging[solv]:
                bar.append(workers_logging[solv][t])
            else:
                bar.append(0)
        lbars.append(bar)

    img = BytesIO()
    index = np.arange(len(solvers))
    bar_width = 0.35
    fig = plt.figure(figsize=(5, 8), dpi=100)
    for i, data, type in zip(range(len(lbars)), lbars, types):
        plt.barh(index + (i * bar_width), data, bar_width, alpha=0.4, label=type)

    plt.ylabel('Solver')
    plt.xlabel('Num probs')
    plt.title(f"Resuelto desde {time.strftime('%Y-%m-%d %H:%M')}")
    ids = [f'Solver-{i + 1}' for i in range(len(solvers))]
    plt.yticks(index + bar_width / 2, ids)
    plt.legend()

    plt.tight_layout()
    plt.savefig(img, format='png')
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()
    plt.close()

    return render_template('logview.html', plot_url=plot_url)


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
    parser.add_argument('--dir', default=None, help="Direccion del servicio de directorio")

    # parsing de los parametros de la linea de comandos
    args = parser.parse_args()

    if not args.verbose:
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

    # Configuration stuff
    if args.port is None:
        port = 9100
    else:
        port = args.port

    if args.open:
        hostname = '0.0.0.0'
        hostaddr = gethostname()
    else:
        hostaddr = hostname = socket.gethostname()

    if args.dir is None:
        raise NameError('A Directory Service addess is needed')
    else:
        diraddress = args.dir

    print('DS Hostname =', hostaddr)

    # Registramos el solver aritmetico en el servicio de directorio
    loggeradd = f'http://{hostaddr}:{port}'
    loggerid = hostaddr.split('.')[0] + '-' + str(port)
    mess = f'REGISTER|{loggerid},LOGGER,{loggeradd}'

    done = False
    while not done:
        try:
            resp = requests.get(diraddress + '/message', params={'message': mess}).text
            done = True
        except ConnectionError:
            print
            pass

    if 'OK' in resp:
        print(f'LOGGER successfully registered')
        # Ponemos en marcha el servidor Flask
        app.run(host=hostname, port=port, debug=False, use_reloader=False)

        mess = f'UNREGISTER|{loggerid}'
        requests.get(diraddress + '/message', params={'message': mess})
    else:
        print('Unable to register')
