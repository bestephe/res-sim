#!/usr/bin/python

import atexit
import glob
import os.path
import random
import subprocess
import sys

###########################
# Parameters. #TODO: Use as inputs?
###########################
NUMPROC=8

#DEGREES = [36, 4]
DEGREES = [4]
MODELS = ['adst', 'edst']
#FAIL = [['edges', [1, 4, 16, 64, 256]], ['vertices', [1, 2, 4, 8, 16]]]
FAIL = [['edges', [0, 1, 4, 16, 64, 256]]]
TOPOS = ['jellyfish', 'egft']
BISECS = ['B1', 'B6']
NUM_HOSTS = [512, 1024, 1536, 2048]
DEFAULT_TREES = [0, 1]
#NUM_TREES = [0, 2, 3, 5, 7] # Resilience + 1
NUM_TREES = [0, 2, 3, 5] # Resilience + 1
#ECMP = [0, 2, 4, 8]
ECMP = [8]
CORR = [True, False]
RUNS = range(1, 2)


###########################
# Build the run string to pass to xargs
###########################
runstrs = []
for num_hosts in NUM_HOSTS:
    for run in RUNS:
        for bisec in BISECS:
            for topo in TOPOS:
                topof = 'topo/' + bisec + '/' + topo + '.' + bisec + '.64r.' + str(num_hosts) + 'h.yaml'
                for fail_model, NUM_FAIL in FAIL:
                    for num_fail in NUM_FAIL:
                        for corr in CORR:
                            for model in MODELS:
                                for ecmp in ECMP:
                                    for degree in DEGREES:
                                        for num_trees in NUM_TREES:
                                            for default_trees in DEFAULT_TREES:
                                                # Nothing to do if there are no trees.
                                                if num_trees == 0 and default_trees == 0:
                                                    continue

                                                tables_prefix = 'tree_tables/' + bisec +  \
                                                    '/tables.' + topo + '.' + bisec + '.64r.' + \
                                                    str(num_hosts) + 'h.' + model + '.nodfr.'
                                                num_tree_str = '%d-t-%dd' % (num_trees, default_trees)

                                                tables_str = tables_prefix + num_tree_str + '.*.json'
                                                tables =  glob.glob(tables_str)
                                                random.shuffle(tables)

                                                if len(tables) == 0:
                                                    print 'Cannot find tables: %s, ignoring...' % tables_str
                                                    continue

                                                if ecmp > 0:
                                                    if len(tables) < ecmp:
                                                        print 'Not enough tables for %d-way ECMP (%s), ignoring...' % (ecmp, tables)
                                                        continue
                                                    tables = tables[:ecmp]

                                                outsuffix = '.'.join(tables_str.split('.')[1:-2])

                                                outf = 'tree_fail_output/' + bisec + '/fail_output.' + \
                                                    outsuffix + '.' + str(degree) + 'd.' + \
                                                    fail_model + '.' + str(num_fail) + 'f.' + \
                                                    str(ecmp) + 'e.'
                                                if corr:
                                                    corrstr = 'c.'
                                                else:
                                                    corrstr = 'nc.'
                                                outf += corrstr
                                                outf += str(run) + '.yaml'

                                                # Quit if we already have results
                                                if os.path.isfile(outf):
                                                    print 'file \'%s\' already exists! Not running this experiment.' % outf
                                                    continue

                                                cmd = './tree_throughput.py' 
                                                cmd += ' --degree ' + str(degree)
                                                cmd += ' --fail ' + fail_model
                                                cmd += ' -n ' + str(num_fail)
                                                if corr:
                                                    cmd += ' -c '
                                                if ecmp > 0:
                                                    cmd += ' -e '
                                                cmd += topof + ' '
                                                cmd += ' '.join(tables)
                                                cmd += ' > ' + outf
                                                #print cmd
                                                runstrs.append(cmd)

#DEBUG
#print runstrs[0]
#sys.exit(1)

# Optional
random.shuffle(runstrs)

increment = NUMPROC * 6
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
