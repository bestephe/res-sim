#!/bin/bash

usage()
{
    echo "usage: $0 output.yaml*"
    exit 1
}


if [ $# -lt 1 ]
then
    usage
fi

for f in $@
do
    ./tcam_state.py $f 2> /dev/null | grep .yaml | awk '{print $1}'
done
