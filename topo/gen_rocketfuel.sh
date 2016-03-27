#!/bin/bash

for f in unpack_rocketfuel/*.r0.cch
do
    outf=$f
    outf=${outf#*/}
    toponum=${outf:0:$((`expr index $outf "*."` - 1))}
    ./cch2yaml.py -o tmp.yaml $f
    numhosts=`grep -- "- uid" tmp.yaml | wc -l | awk '{print $1}'`
    rm tmp.yaml
    ./cch2yaml.py -o rocketfuel/rocketfuel._.$toponum.${numhosts}h.yaml $f
done
