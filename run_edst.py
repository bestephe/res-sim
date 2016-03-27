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
BISECS = ['B1', 'B6']
NUM_HOSTS = [1024, 1536, 2048, 3072]
#NUM_HOSTS = [1024]
#NUM_HOSTS = [1536, 2048, 3072]
#NUM_HOSTS = [4096]
#NUM_HOSTS = [2048]
#NUM_TREES = [4, 8, -1]
NUM_TREES = [8]
#NUM_TREES = [8]
TABLE_NUMS = range(1, 10)
#TTGs = ['nodfr', 'line', 'nores', 'mlayer', 'alayer']
#TTGs = ['mlayer', 'alayer', 'nodfr', 'line', 'nores', 'T']
#TTGs = ['mlayer', 'alayer', 'line', 'nores', 'T']
TTGs = ['mlayer', 'alayer', 'T']
#MAX_L1_WIDTHS = [2, 3, 4]
MAX_L1_WIDTHS = [4, 5, 6]
L1_WIDTHS_DICT = {
    'B1': [8, 12, 16],
    'B6': [6, 8, 10],
    'B12': [4, 6, 8],
}
SELF_LAYER = ['no-self-layer', 'sl-perf', 'sl-res']


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
                        
                        # Get the l1widths
                        if ttg in ('mlayer', 'alayer', 'T'):
                        #    x = int(math.ceil(math.log(max_trees, 2)))
                        #    l1widths = [2**i for i in range(1, x)]
                        #    assert (l1widths[-1] <= max_trees)
                        #    #l1widths.append(max_trees)
                            l1widths = [x for x in L1_WIDTHS_DICT[bisec] if x <= max_trees]
                        else:
                            l1widths = [0]

                        #print 'l1widths:', l1widths

                        for l1width in l1widths:
                            for maxl1 in MAX_L1_WIDTHS:
                                for self_layer in SELF_LAYER:
                                    # Get the ttg string
                                    if ttg in ('mlayer', 'alayer', 'T'):
                                        ttg_str = ttg + '-%d' % l1width
                                    else:
                                        ttg_str = ttg
                                        if self_layer != 'no-self-layer':
                                            continue

                                    if self_layer == 'no-self-layer':
                                        sl_str = ''
                                    else:
                                        sl_str = '-' + self_layer
                                        if ttg not in ('mlayer', 'alayer', 'T'):
                                            continue

                                    # Get the suffix for the state and forwarding table output files
                                    out_suffix = topo + '.' + bisec + '.64r.' + \
                                        str(num_hosts) + 'h.' + 'edst.' + ttg_str + \
                                        '.' + str(num_trees) + '-t-' + str(maxl1) + 'ml1' + \
                                        sl_str + '.' + str(table_num) +  '.json'
                                    #if num_trees > 0:
                                    #else:
                                    #    out_suffix = topo + '.' + bisec + '.64r.' + \
                                    #        str(num_hosts) + 'h.' + 'edst.' + ttg_str + \
                                    #        '.' + str(table_num) +  '.json'

                                    # Get the output file names
                                    statef = 'tree_output/' + bisec + '/state.' + out_suffix
                                    tablef = 'tree_tables/' + bisec + '/tables.' + out_suffix

                                    # ./tree_alg.py --model edst -t alayer --dfr --l1width 4 -w tree_tables/jellyfish.B1.8r.16h.edst.dfr.alayer-4.json -o tree_output/jellyfish.B1.8r.16h.edst.dfr.alayer-4.json  topo/jellyfish.B1.8r.16h.yaml

                                    cmd = './tree_alg.py --model edst'
                                    if ttg != 'nodfr':
                                        cmd += ' --dfr'
                                        cmd += ' --ttg-type ' + ttg
                                        cmd += ' --l1width ' + str(l1width)
                                    cmd += ' --num-trees ' + str(num_trees)
                                    if (num_trees > 0):
                                        cmd += ' --maxl1 ' + str(maxl1)
                                    if self_layer == 'sl-perf':
                                        cmd += ' --self-layer'
                                        cmd += ' --ttg-sort perf'
                                    elif self_layer == 'sl-res':
                                        cmd += ' --self-layer'
                                        cmd += ' --ttg-sort res'
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
