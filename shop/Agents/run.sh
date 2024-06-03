#!/bin/bash

python DirectoryService.py &
sleep 1
python userAgent.py &
python BuscadorAgent.py &
python ComercianteAgent.py &
python FinancieroAgent.py &
python GestorExternoAgent.py &
python PersonalVendedorExternoAgent.py &
python GestorDevolucionesAgent.py &
python TransportistaDevolucionesAgent.py &
python DirectoryServiceTransportistes.py &
sleep 1
python TransportistaAgent_1.py &
sleep 1
#python TransportistaAgent_2.py &
#sleep 1
python CentroLogisticoDirectoryService.py &
sleep 1
python CentroLogisticoAgent1.py &
sleep 1
#python CentroLogisticoAgent2.py