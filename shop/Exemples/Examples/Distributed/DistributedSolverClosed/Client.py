"""
.. module:: Client

Client
*************

:Description: Client

    Cliente del resolvedor distribuido

:Authors: bejar
    

:Version: 

:Created on: 06/02/2018 8:21 

"""

from Util import gethostname
import socket
import argparse
from AgentUtil.FlaskServer import shutdown_server
import requests
from flask import Flask, request, render_template, url_for, redirect
import logging

__author__ = 'bejar'

app = Flask(__name__)

problems = {}
probcounter = 0
clientid = ''
diraddress = ''


@app.route("/message", methods=['GET', 'POST'])
def message():
    """
    Entrypoint para todas las comunicaciones

    :return:
    """
    global problems

    # if request.form.has_key('message'):
    if 'message' in request.form:
        send_message(request.form['problem'], request.form['message'])
        return redirect(url_for('.iface'))
    else:
        # Respuesta del solver SOLVED|PROBID,SOLUTION
        mess = request.args['message'].split('|')
        if len(mess) == 2:
            messtype, messparam = mess
            if messtype == 'SOLVED':
                solution = messparam.split(',')
                if len(solution) == 2:
                    probid, sol = solution
                    if probid in problems:
                        problems[probid][2] = sol
                    else:  # Para el script de test de stress
                        problems[probid] = ['DUMMY', 'DUMMY', sol]
        return 'OK'


@app.route('/info')
def info():
    """
    Entrada que da informacion sobre el agente a traves de una pagina web
    """
    global problems

    return render_template('clientproblems.html', probs=problems)


@app.route('/iface')
def iface():
    """
    Interfaz con el cliente a traves de una pagina de web
    """
    probtypes = ['ARITH', 'MFREQ']
    return render_template('iface.html', types=probtypes)


@app.route("/stop")
def stop():
    """
    Entrada que para el agente
    """
    shutdown_server()
    return "Parando Servidor"


def send_message(probtype, problem):
    """
    Envia un request a un solver

    mensaje:

    SOLVE|TYPE,PROBLEM,PROBID,CLIENTID

    :param probid:
    :param probtype:
    :param proble:
    :return:
    """
    global probcounter
    global clientid
    global diraddress
    global port
    global problems

    probid = f'{clientid}-{probcounter:03}'
    probcounter += 1

    solveradd = requests.get(diraddress + '/message', params={'message': 'SEARCH|SOLVER'}).text

    if 'OK' in solveradd:
        # Le quitamos el OK de la respuesta
        solveradd = solveradd[4:]

        problems[probid] = [probtype, problem, 'PENDING']
        mess = f'SOLVE|{probtype},{clientadd},{probid},{sanitize(problem)}'
        resp = requests.get(solveradd + '/message', params={'message': mess}).text
        if 'ERROR' not in resp:
            problems[probid] = [probtype, problem, 'PENDING']
        else:
            problems[probid] = [probtype, problem, 'FAILED SOLVER']
    else:
        problems[probid] = (probtype, problem, 'FAILED DS')


def sanitize(prob):
    """
    remove problematic punctuation signs from the string of the problem
    :param prob:
    :return:
    """
    return prob.replace(',', '*')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--open', help="Define si el servidor esta abierto al exterior o no", action='store_true',
                        default=False)
    parser.add_argument('--verbose', help="Genera un log de la comunicacion del servidor web", action='store_true',
                        default=False)
    parser.add_argument('--port', default=None, type=int, help="Puerto de comunicacion del agente")
    parser.add_argument('--dir', default=None, help="Direccion del servicio de directorio")

    # parsing de los parametros de la linea de comandos
    args = parser.parse_args()

    if not args.verbose:
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

   # Configuration stuff
    if args.port is None:
        port = 9001
    else:
        port = args.port

    if args.open:
        hostname = '0.0.0.0'
        hostaddr = gethostname()
    else:
        hostaddr = hostname = socket.gethostname()

    print('DS Hostname =', hostaddr)

    clientadd = f'http://{hostaddr}:{port}'
    clientid = hostaddr.split('.')[0] + '-' + str(port)

    if args.dir is None:
        raise NameError('A Directory Service addess is needed')
    else:
        diraddress = args.dir

    # Ponemos en marcha el servidor Flask
    app.run(host=hostname, port=port, debug=False, use_reloader=False)
