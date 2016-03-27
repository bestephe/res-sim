#!/bin/bash

float_scale=5
function float_eval()
{
    local stat=0
    local result=0.0
    if [[ $# -gt 0 ]]; then
        result=$(echo "scale=$float_scale; $*" | bc -q 2>/dev/null)
        stat=$?
        if [[ $stat -eq 0  &&  -z "$result" ]]; then stat=1; fi
    fi
    echo $result
    return $stat
}

#for radix in 16 32 48 64;
#for radix in 32 48 64;
for radix in 64;
do
    #for bisec in 1 6 12
    #for bisec in 6 12
    for bisec in 12
    do
        ratio=$(float_eval 1.0/$bisec)
        #for numhosts in 128 256 512 1024 2048;
        #for numhosts in 4096 8192;
        #for numhosts in 256;
        #for numhosts in 256 512 1024 2048 4096;
        for numhosts in 8192;
        do
            #./topo_gen.py -o B$bisec/jellyfish.B$bisec.${radix}r.${numhosts}h.yaml --num-hosts $numhosts jellyfish `./topo_opt.py -n $numhosts -b $ratio -r $radix jellyfish`;

            ./topo_gen.py -o B$bisec/egft.B$bisec.${radix}r.${numhosts}h.yaml --num-hosts $numhosts egft "`pypy ./topo_opt.py -n $numhosts -b $ratio -r $radix egft`";
        done
    done
done
