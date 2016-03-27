#!/usr/bin/python

import atexit
import glob
import math
import random
import subprocess
import sys

###########################
# Parameters. #TODO: Use as inputs?
###########################
NUMPROC=4

TOPOS = ['jellyfish', 'egft']
BISECS = ['B1', 'B6']
#NUM_HOSTS = [1024, 1536, 2048, 3072]
#NUM_HOSTS = [512]
NUM_HOSTS = [512, 1024, 1536, 2048, 3072]
#NUM_HOSTS = [1024, 1536, 2048]
#NUM_HOSTS = [1024]
#NUM_HOSTS = [1536, 2048, 3072]
#NUM_HOSTS = [4096]
#NUM_HOSTS = [2048]
#NUM_TREES = [4, 8, -1]
#NUM_TREES = [4, 8]
#NUM_TREES = [8, -1]
DEFAULT_TREES = [0, 1]
#NUM_TREES = [0, 2, 3, 5, 7] # Resilience + 1
#NUM_TREES = [0, 2, 3, 5] # Resilience + 1
NUM_TREES = [0, 2, 3] # Resilience + 1
TABLE_NUMS = range(1, 10)

# The filename lies.  This now runs nodfr edst resilience as well.  I should
# change the filename.
MODELS = ['adst', 'edst']


###########################
# Build the run string to pass to xargs
###########################
runstrs = []
for num_hosts in NUM_HOSTS:
    for bisec in BISECS:
        for topo in TOPOS:
            topof = 'topo/' + bisec + '/' + topo + '.' + bisec + '.64r.' + str(num_hosts) + 'h.yaml'

            for table_num in TABLE_NUMS:
                for default_trees in DEFAULT_TREES:
                    for model in MODELS:
                        for num_trees in NUM_TREES:
                            # Nothing to do if there are no trees.
                            if num_trees == 0 and default_trees == 0:
                                continue

                            # Get the suffix for the state and forwarding table output files
                            if num_trees > 0:
                                out_suffix = topo + '.' + bisec + '.64r.' + \
                                    str(num_hosts) + 'h.' + model + '.nodfr.' + \
                                    str(num_trees) + '-t-' + str(default_trees) + 'd.' + \
                                    str(table_num) +  '.json'
                            else:
                                out_suffix = topo + '.' + bisec + '.64r.' + \
                                    str(num_hosts) + 'h.' + model + '.nodfr.' + \
                                    'max-t-' + str(default_trees) + 'd.' + \
                                    str(table_num) +  '.json'

                            # Get the output file names
                            statef = 'tree_output/' + bisec + '/state.' + out_suffix
                            tablef = 'tree_tables/' + bisec + '/tables.' + out_suffix

                            cmd = './tree_alg.py '
                            cmd += ' --model ' + model
                            cmd += ' --num-trees ' + str(num_trees)
                            cmd += ' --default-trees ' + str(default_trees)
                            cmd += ' -o ' + statef
                            cmd += ' -w ' + tablef
                            cmd += ' ' + topof

                            #print cmd
                            runstrs.append(cmd)

# Optional to try to even out the workload
random.shuffle(runstrs)

#DEBUG
#print runstrs[0]
#sys.exit(1)

increment = NUMPROC * 20
for i in range(0, len(runstrs), increment):
    print i, i+increment, 'out of', len(runstrs)
    print len(runstrs[i:i+increment])
    print

    #runstr = 'ulimit -Sv 3500000; ' # 4.5GB memory limit
    runstr = ''
    runstr += 'echo -e ' 
    runstr += '\'\n' + '\n'.join(runstrs[i:i+increment]) + '\''
    runstr += ' | xargs -I CMD -P %d bash -c CMD' % (NUMPROC)

    #print runstr
    subprocess.call(runstr, shell=True)

"""
#runstr = 'ulimit -Sv 3500000; ' # 4.5GB memory limit
runstr = ''
runstr += 'echo -e ' 
runstr += '\'\n' + '\n'.join(runstrs) + '\''
runstr += ' | xargs -I CMD -P %d bash -c CMD' % (NUMPROC)

#print runstr
subprocess.call(runstr, shell=True)
"""
