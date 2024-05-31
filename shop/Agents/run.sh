#!/bin/bash

python DirectoryService.py &
sleep 2
#python userAgent.py &
#sleep 1
python BuscadorAgent.py &
sleep 1
python ComercianteAgent.py &
sleep 1
#python FinancieroAgent.py &
#sleep 1
python GestorExternoAgent.py &
sleep 1
python PersonalVendedorExternoAgent.py