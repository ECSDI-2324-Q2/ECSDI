"""
.. module:: StressTest

StressTest
*************

:Description: StressTest

    Manda peticiones a los solver como si fuera el cliente

    Un cliente que este en marcha recibira las respuestas

:Authors: bejar
    

:Version: 

:Created on: 07/02/2018 13:26 

"""

import argparse
import requests
import random, string
import socket

__author__ = 'bejar'

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--n', default=100, type=int, help="Numero de iteraciones del test")
    parser.add_argument('--cport', default=None, help="Puerto del cliente que recibe las respuestas")
    parser.add_argument('--dir', default=None, help="Direccion del servicio de directorio")

    # parsing de los parametros de la linea de comandos
    args = parser.parse_args()

    probcounter = 0
    diraddress = args.dir
    clientaddress = f'http://{socket.gethostname()}:{args.cport}' #args.client
    testid = ''.join(random.choice(string.ascii_lowercase) for i in range(10))

    for i in range(args.n):
        print(f'TEST {i}')
        probcounter += 1

        solveradd = requests.get(diraddress + '/message', params={'message': 'SEARCH|SOLVER'}).text

        if 'OK' in solveradd:
            # Le quitamos el OK de la respuesta
            solveradd = solveradd[4:]
            probid = f'TESTARITH-{testid}-{probcounter:03}'
            mess = f'SOLVE|ARITH,{clientaddress},{probid},{i}+{i}'
            resp = requests.get(solveradd + '/message', params={'message': mess}, timeout=5).text
            probid = f'TESTMFREQ-{testid}-{probcounter}'
            mess = f"SOLVE|MFREQ,{clientaddress},{probid},{''.join(random.choice(string.ascii_lowercase) for i in range(500))}"
            resp = requests.get(solveradd + '/message', params={'message': mess}, timeout=5).text
