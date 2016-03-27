#!/usr/bin/python

import atexit
import glob
import random
import subprocess
import sys

###########################
# Parameters. #TODO: Use as inputs?
###########################
NUMPROC=3

BISECS = ['B1', 'B2', 'B6']
#BISECS = ['B6']
MODELS = ['plinko-c-dfr', 'plinko-nc-dfr']
TOPOS = ['jellyfish', 'egft']
#TOPOS = ['jellyfish']
#TOPOS = ['egft']
NUM_HOSTS = [512, 1024, 2048]
#RES = [1]
RES = [0, 1, 2, 4]
#ECMP = [1, 2, 4, 8]
ECMP = [1, 2, 4]
FAS = [True]
#FAS = [True, False]


###########################
# Build the run string to pass to xargs
###########################
runstrs = []
for num_hosts in NUM_HOSTS:
    for bisec in BISECS:
        for topo in TOPOS:
            topof = 'topo/' + bisec + '/' + topo + '.' + bisec + '.64r.' + str(num_hosts) + 'h.yaml'
            for res in RES:
                for ecmp in ECMP:
                    for fas in FAS:
                        for model in MODELS:
                            tables =  glob.glob('tables/' + bisec +'/' + topo + \
                                '.' + bisec + '.64r.' + str(num_hosts) + 'h.' + \
                                model + '.' + str(res) + 'res.*.json')
                            random.shuffle(tables)
                            if ecmp > 0:
                                tables = tables[:ecmp]

                            outf = 'dfr_output/' + bisec + '/' + topo + '.' + \
                                str(num_hosts) + 'h.' + model + '.' + \
                                str(res) + 'res.' + str(ecmp) + 'e.'
                            if fas:
                                outf += 'fas.'
                            outf += 'yaml'

                            fixmodel = 'plinko' if model.startswith('plinko') else model
                            cmd = './resnet_dfr.py --model ' + fixmodel
                            if fas:
                                cmd += ' --fas '
                            cmd += ' ' + topof + ' '
                            cmd += ' '.join(tables)
                            cmd += ' > ' + outf
                            #print cmd
                            runstrs.append(cmd)

# Optional
random.shuffle(runstrs)

# Run in batches to avoid an OSError "Argument list is too long"
step = 8 * NUMPROC
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

