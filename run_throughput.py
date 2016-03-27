#!/usr/bin/python

import atexit
import glob
import random
import subprocess
import sys

###########################
# Parameters. #TODO: Use as inputs?
###########################
NUMPROC=8

BISECS = ['B1', 'B2', 'B6']
#BISECS = ['B6']
DEGREE = 36
#DEGREE = 4
#MODELS = ['plinko', 'eth-fcp']
#MODELS = ['plinko-c', 'plinko-nc']
MODELS = ['plinko-c-dfr', 'plinko-nc-dfr']
#MODELS = ['plinko-c']
#MODELS = ['eth-fcp']
#FAIL = [['edges', [1, 4, 16, 64, 256]], ['vertices', [1, 2, 4, 8, 16]]]
FAIL = [['edges', [0, 1, 4, 16, 64, 256]]]
#FAIL = [['vertices', [1, 2, 4, 8, 16]]]
TOPOS = ['jellyfish', 'egft']
#TOPOS = ['jellyfish']
#TOPOS = ['egft']
#FAIL = [['edges', [0, 1, 4, 16, 64, 256]]]
#FAIL = [['edges', [0, 1, 4]]]
#FAIL = [['edges', [16, 64, 256]]]
#FAIL = [['vertices', [1, 2, 4, 8, 16]]]
#TOPOS = ['jellyfish']
#NUM_HOSTS = [256, 512, 1024, 2048]
NUM_HOSTS = [512, 1024, 2048]
#NUM_HOSTS = [1024]
#NUM_HOSTS = [2048]
RES = [0, 2, 4]
#RES = [2, 4]
#RES = [1]
#RES = [0, 2]
#RES = [0, 2, 4, 6]
#RES = [6]
#RES = [0, 2, 4, 8, 16, 32]
#RES = [2, 8, 32]
#RES = [0, 2, 4, 8]
#RES = [4]
#RES = [4, 8]
#ECMP = [0]
#ECMP = [0, 2, 4, 8]
ECMP = [8]
CORR = [True, False]

#procs = []
#def cleanup():
#    for p in procs:
#        p.kill()


###########################
# Build the run string to pass to xargs
###########################
runstrs = []
for num_hosts in NUM_HOSTS:
    for bisec in BISECS:
        for topo in TOPOS:
            topof = 'topo/' + bisec + '/' + topo + '.' + bisec + '.64r.' + str(num_hosts) + 'h.yaml'
            for fail_model, NUM_FAIL in FAIL:
                for num_fail in NUM_FAIL:
                    for res in RES:
                        for ecmp in ECMP:
                            for corr in CORR:
                                for model in MODELS:
                                    tables =  glob.glob('tables/' + bisec +'/' + topo + \
                                        '.' + bisec + '.64r.' + str(num_hosts) + 'h.' + \
                                        model + '.' + str(res) + 'res.*.json')
                                    random.shuffle(tables)
                                    if ecmp > 0:
                                        tables = tables[:ecmp]

                                    outf = 'fail_output/' + bisec + '/' + topo + '.' + \
                                        str(num_hosts) + 'h.' + model + '.' + \
                                        str(res) + 'res.' + str(DEGREE) + 'd.' + \
                                        fail_model + '.' + str(num_fail) + 'f.' + \
                                        str(ecmp) + 'e.'
                                    if corr:
                                        corrstr = 'c.'
                                    else:
                                        corrstr = 'nc.'
                                    outf += corrstr
                                    outf += 'yaml'

                                    fixmodel = 'plinko' if model.startswith('plinko') else model
                                    cmd = './resnet_throughput.py --model ' + fixmodel
                                    cmd += ' --degree ' + str(DEGREE)
                                    cmd += ' --fail ' + fail_model
                                    cmd += ' -n ' + str(num_fail)
                                    cmd += ' -t '
                                    if corr:
                                        cmd += ' -c '
                                    if ecmp > 0:
                                        cmd += ' -e '
                                    cmd += topof + ' '
                                    cmd += ' '.join(tables)
                                    cmd += ' > ' + outf
                                    #print cmd
                                    runstrs.append(cmd)

# Run in batches to avoid an OSError "Argument list is too long"
step = 5 * NUMPROC
for i in range(0, len(runstrs), step):
    #runstr = 'ulimit -Sv 3500000; ' # 4.5GB memory limit
    runstr = ''
    runstr += 'echo -e ' 
    runstr += '\'\n' + '\n'.join(runstrs[i:i+step]) + '\''
    runstr += ' | xargs -I CMD -P %d bash -c CMD' % (NUMPROC)

    #print runstr
    subprocess.call(runstr, shell=True)

    #DEBUGGING 
    """
    for index in ((i-1), i):
        outf = runstrs[index].split(' ')[-1]
        print
        print 'i:', index
        print outf
        runstr = 'ls %s' % outf
        subprocess.call(runstr, shell=True)
    """

