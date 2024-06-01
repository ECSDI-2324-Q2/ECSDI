#!/bin/bash

python DirectoryService.py &
sleep 2
python userAgent.py &
sleep 1
python BuscadorAgent.py &
sleep 1
python ComercianteAgent.py &
sleep 1
python FinancieroAgent.py &
sleep 1
python GestorExternoAgent.py &
sleep 1
python PersonalVendedorExternoAgent.py &
sleep 1
python GestorDevolucionesAgent.py &
sleep 1
python TransportistaDevolucionesAgent.py &
sleep 1
python DirectoryServiceTransportistes.py &
sleep 2
python TransportistaAgent_1.py &
sleep 1
python CentroLogisticoDirectoryService.py &
sleep 2
python CentroLogisticoAgent.py