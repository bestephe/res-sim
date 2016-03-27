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
NUMPROC=8

TOPOS = ['jellyfish', 'egft']
BISECS = ['B1', 'B2', 'B6']
#NUM_HOSTS = [1024, 1536, 2048]
NUM_HOSTS = [1024, 1536, 2048, 3072]
NUM_TREES = [4, 6, 8]
TABLE_NUMS = range(1, 10)
TTGs = ['rand', 'maxdag']
RAND_RES = [0, 1, 2, 3]
TTG_SORT = ['perf', 'res']


###########################
# Build the run string to pass to xargs
###########################
runstrs = []
for num_hosts in NUM_HOSTS:
    for bisec in BISECS:
        for topo in TOPOS:
            topof = 'topo/' + bisec + '/' + topo + '.' + bisec + '.64r.' + str(num_hosts) + 'h.yaml'

            # Find the maximum number of trees 
            def get_trees():
                out = subprocess.check_output('./tree_alg.py -m --model edst ' + topof, shell=True)
                return int(out.split()[0])
            max_trees = max([get_trees() for _i in range(10)])
            print 'max_trees:', max_trees

            UPDATED_NUM_TREES = [x for x in NUM_TREES if x < max_trees]
            if len(UPDATED_NUM_TREES) == 0:
                UPDATED_NUM_TREES = [max_trees]
            print 'UPDATED_NUM_TREES:', UPDATED_NUM_TREES

            for table_num in TABLE_NUMS:
                for ttg in TTGs:
                    for num_trees in UPDATED_NUM_TREES:
                        for rand_res in RAND_RES:
                            for ttg_sort in TTG_SORT:
                                ttg_str = '%s-r%d-%s' % (ttg, rand_res, ttg_sort)

                                # Get the suffix for the state and forwarding table output files
                                out_suffix = topo + '.' + bisec + '.64r.' + \
                                    str(num_hosts) + 'h.' + 'edst.' + ttg_str + \
                                    '.' + str(num_trees) + '-t.' + str(table_num) +  '.json'

                                # Get the output file names
                                statef = 'tree_output/' + bisec + '/state.' + out_suffix
                                tablef = 'tree_tables/' + bisec + '/tables.' + out_suffix

                                # ./tree_alg.py --model edst -t alayer --dfr --l1width 4 -w tree_tables/jellyfish.B1.8r.16h.edst.dfr.alayer-4.json -o tree_output/jellyfish.B1.8r.16h.edst.dfr.alayer-4.json  topo/jellyfish.B1.8r.16h.yaml

                                cmd = './tree_alg.py --model edst'
                                cmd += ' --dfr'
                                cmd += ' --ttg-type ' + ttg
                                cmd += ' --ttg-sort ' + ttg_sort
                                cmd += ' --rand-res ' + str(rand_res)
                                cmd += ' --num-trees ' + str(num_trees)
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
