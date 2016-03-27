#!/bin/bash

###########################
# Parse arguments
###########################
usage()
{
    echo "usage: $0 {edges, vertices} topo+"
    exit 1
}

if [ $# -lt 2 ]
then
    usage
elif [ $1 != "edges" ] && [ $1 != 'vertices' ]
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
NUMPROC=8
#ts=`date +%F-%T`
failmode=$1
topos=${@:2}

#cd topo
#./gen_topos.sh
#cd ..

runstr=""
#for fail in {0..5}
#for fail in 0 1 2 4 6
for fail in 0 1 2 4
do
    for topo in $topos
    do
        #for model in plinko mpls-frr eth-fcp
        for model in plinko
        #for model in eth-fcp
        do
            for fwdr in src hop-by-hop
            #for fwdr in src
            do
                for iter in {1..1}
                do
                    # Remove topo/B0.2 and find the outdir
                    outf=$topo
                    outf=${outf#*/}
                    outdir=${outf:0:`expr index $outf "*/"`}
                    outf=${outf#*/}


                    if [ $model = "plinko" ]
                    then
                        # XXX: Ugly copypasta for Plinko with and without
                        # compression aware routing. Comment for non-plinko
                        outf=${outf//.yaml/.${fail}f.$failmode.$model-nc.$fwdr.$iter.yaml}
                        cmd="python ./resnet_alg.py -r $fail --fail $failmode --model $model --fwd-routing $fwdr $topo > output/$outdir/$outf"
                        runstr="${runstr}$cmd\n"

                        outf=$topo
                        outf=${outf#*/}
                        outdir=${outf:0:`expr index $outf "*/"`}
                        outf=${outf#*/}
                        outf=${outf//.yaml/.${fail}f.$failmode.$model-c.$fwdr.$iter.yaml}
                        cmd="python ./resnet_alg.py -c -r $fail --fail $failmode --model $model --fwd-routing $fwdr $topo > output/$outdir/$outf"
                        runstr="${runstr}$cmd\n"
                    else
                        outf=${outf//.yaml/.${fail}f.$failmode.$model.$fwdr.$iter.yaml}
                        cmd="python ./resnet_alg.py -r $fail --fail $failmode --model $model --fwd-routing $fwdr $topo > output/$outdir/$outf"
                        runstr="${runstr}$cmd\n"
                    fi

                done
            done
        done
    done
done

ulimit -Sv 4000000 # 4.0GB memory limit
echo -e $runstr | xargs -I CMD -P $NUMPROC bash -c CMD
