#!/bin/bash

# Define the array of ports
ports=(9000 9002 9003 9004 9081 9030 9087 9042 9005 9006 9009)

# Loop over each port
for port in ${ports[@]}
do
  # Get the process IDs of the processes using the port
  pids=$(lsof -t -i:$port)

  # Kill each process
  for pid in $pids
  do
    kill -9 $pid
  done
done