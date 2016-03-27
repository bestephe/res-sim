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
NUMPROC=5

#DEGREES = [36, 4]
DEGREES = [4]
#TTGs = ['mlayer', 'alayer', 'nodfr', 'line', 'nores', 'T']
TTGs = ['mlayer', 'alayer', 'T']
#TTGs = ['nores', 'nodfr']
#FAIL = [['edges', [1, 4, 16, 64, 256]], ['vertices', [1, 2, 4, 8, 16]]]
FAIL = [['edges', [0, 1, 4, 16, 64, 256]]]
TOPOS = ['jellyfish', 'egft']
BISECS = ['B1', 'B6']
#BISECS = ['B12', 'B6', 'B1']
#BISECS = ['B1']
NUM_HOSTS = [1024]
#NUM_HOSTS = [1536, 2048]
#NUM_HOSTS = [1536, 2048, 3072]
#NUM_HOSTS = [1024, 1536, 2048]
#NUM_HOSTS = [4096]
#NUM_TREES = [4, 8, -1]
NUM_TREES = [8]
#ECMP = [0, 2, 4, 8]
ECMP = [8]
CORR = [True, False]
RUNS = range(1, 2)

#MAX_L1_WIDTHS = [2, 3, 4]
MAX_L1_WIDTHS = [4, 5, 6]
L1_WIDTHS_DICT = {
    'B1': [8, 12, 16],
    'B6': [6, 8, 10],
    'B12': [4, 6, 8],
}
SELF_LAYER = ['no-self-layer', 'sl-perf', 'sl-res']

#procs = []
#def cleanup():
#    for p in procs:
#        p.kill()


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
                            for ttg in TTGs:
                                for ecmp in ECMP:
                                    for degree in DEGREES:
                                        for num_trees in NUM_TREES:
                                            for maxl1 in MAX_L1_WIDTHS:
                                                for self_layer in SELF_LAYER:
                                                    tables_prefix = 'tree_tables/' + bisec +  \
                                                        '/tables.' + topo + '.' + bisec + '.64r.' + \
                                                        str(num_hosts) + 'h.edst.'

                                                    if ttg in ('mlayer', 'alayer', 'T'):
                                                        tmp_tables = glob.glob(tables_prefix + \
                                                            ttg + '*.*.json')
                                                        tmp_tables = map(lambda x: x.split('.')[6], tmp_tables)
                                                        ttg_strs = list(set(tmp_tables))
                                                        #print 'before:', ttg_strs

                                                        ttg_strs = filter(lambda x: int(x.split('-')[1]) in L1_WIDTHS_DICT[bisec], ttg_strs)
                                                        #print 'after:', ttg_strs
                                                    else:
                                                        ttg_strs = [ttg]

                                                    if self_layer == 'no-self-layer':
                                                        sl_str = ''
                                                    else:
                                                        sl_str = '-' + self_layer
                                                        if ttg not in ('mlayer', 'alayer', 'T'):
                                                            continue

                                                    for ttg_str in ttg_strs:
                                                        tables_str = tables_prefix + ttg_str + '.' + str(num_trees) + '-t-' + \
                                                            str(maxl1) + 'ml1' + sl_str + '.*.json'
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
