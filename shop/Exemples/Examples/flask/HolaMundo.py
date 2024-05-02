"""
.. module:: HolaMundo

HolaMundo
*************

:Description: HolaMundo

    

:Authors: bejar
    

:Version: 

:Created on: 28/02/2018 13:56 

"""

__author__ = 'bejar'

from flask import Flask

app = Flask(__name__)


@app.route('/')
def hello():
    return "Hello, World!"


if __name__ == '__main__':
    app.run()
