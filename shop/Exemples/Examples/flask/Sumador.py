# -*- coding: utf-8 -*-
"""
Created on Thu Dec 26 10:47:57 2013

Webservice flask con una entrada

/sumador - Retorna la suma de los dos numeros que se pasan como parametros x e y de la peticion

por defecto el servidor flask se pondra en marcha en http://127.0.0.1:5000/

Se puede invocar al servicio desde un navegador

http://127.0.0.1:5000/sumador?x=3&y=4

@author: javier
"""

from flask import Flask, request

__author__ = 'bejar'

app = Flask(__name__)


@app.route("/sumador")
def servicio():
    x = int(request.args['x'])
    y = int(request.args['y'])
    return str(x + y)


if __name__ == '__main__':
    app.run()
