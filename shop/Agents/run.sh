#!/bin/bash

./stop.sh

python DirectoryService.py &
sleep 1
python userAgent.py &
sleep 0.1
python BuscadorAgent.py &
sleep 0.1
python ComercianteAgent.py &
sleep 0.1
python FinancieroAgent.py &
sleep 0.1
python GestorExternoAgent.py &
sleep 0.1
python PersonalVendedorExternoAgent.py &
sleep 0.1
python GestorDevolucionesAgent.py &
sleep 0.1
python TransportistaDevolucionesAgent.py &
sleep 0.1
python DirectoryServiceTransportistes.py &
sleep 1
python TransportistaAgent_1.py &
sleep 0.1
python TransportistaAgent_2.py &
sleep 0.1
python CentroLogisticoDirectoryService.py &
sleep 1
python CentroLogisticoAgent1.py &
sleep 1
python CentroLogisticoAgent2.py