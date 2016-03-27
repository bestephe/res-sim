#!/bin/bash

NUMPROC=8

TOPODIR="../topo"

BISECS="B1 B6"
RADICES="64"
#HOSTS="256 512 1024 2048 4096 8192"
HOSTS="256 512 1024 2048"
#HOSTS="256 512 1024"
#HOSTS="1024"
#HOSTS="256 512"
#HOSTS=4096
NUMTABLES="8"
#NUMTABLES="32"
#NUMTABLES="42"
#NUMTABLES="54"
#NUMTABLES="1"
#MODELS="plinko eth-fcp"
MODELS="plinko-c plinko-nc"
#RESILIENCY="0 2 4 6 8"
#RESILIENCY="0 2 4 6"
RESILIENCY="1"
#RESILIENCY="8 10"
#RESILIENCY="16 32"
#RESILIENCY="0 2 4 8 16 32"
#RESILIENCY="0 2 4"
#RESILIENCY="0 2 6 8"
#RESILIENCY="0"
#RESILIENCY="6 8"

runstr=""
for res in $RESILIENCY
do
    for bisec in $BISECS
    do
        for rad in $RADICES
        do
            for host in $HOSTS
            do
                for (( numt=1; numt<=$NUMTABLES; numt++ ))
                do
                    for model in $MODELS
                    do
                        topos=$TOPODIR/$bisec/*.$bisec.${rad}r.${host}h.yaml
                        for topo in $topos
                        do
                            outf=$topo
                            outf=${outf#*/}
                            outf=${outf#*/}
                            outf=${outf//.yaml/.$model.${res}res.$numt.json}

                            if [[ $model == "eth-fcp" ]]
                            then
                                fixmodel="eth-fcp --fwd-routing hop-by-hop"
                            elif [[ $model == "plinko-c" ]]
                            then
                                fixmodel="plinko -c"
                            elif [[ $model == "plinko-nc" ]]
                            then
                                fixmodel="plinko"
                            else
                                fixmodel="error"
                            fi

                            cmd="../resnet_alg.py --fail edges --model $fixmodel -r $res -w $outf $topo "
                            #cmd="../resnet_alg.py --fail vertices --model $fixmodel -r $res -w $outf $topo "
                            #echo $topo
                            #echo $outf
                            #echo $cmd
                            #echo

                            runstr="${runstr}$cmd\n"
                        done
                    done
                done
            done
        done
    done
done

#ulimit -Sv 2500000 # 1.5GB memory limit
echo -e $runstr | xargs -I CMD -P $NUMPROC bash -c CMD #> /dev/null
