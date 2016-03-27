#!/bin/bash

###########################
# Parse arguments
###########################
usage()
{
    echo "usage: $0 missing.txt"
    exit 1
}

if [ $# -ne 1 ]
then
    usage
fi


###########################
# Clean exit
###########################
cleanup()
# example cleanup function
{
  kill $(jobs -p)
  return $?
}

control_c()
# run if user hits control-c
{
  echo -en "\n*** Ouch! Exiting ***\n"
  exit $?
}

# trap keyboard interrupt (control-c)
trap control_c SIGINT
# kill background jobs
trap cleanup EXIT


###########################
# Run the program
###########################
NUMPROC=4

ulimit -Sv 300000 # 3GB virtual memory limit
cat $1 | xargs -I CMD -P $NUMPROC bash -c CMD
