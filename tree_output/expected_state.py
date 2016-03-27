#!/usr/bin/python

import glob
import subprocess
import sys
import yaml

#BISECS = ['B1', 'B6', 'B12']
BISECS = ['B1']
TOPOS = ['jellyfish', 'egft']
TOPO_SIZES = [256, 512, 1024, 2048, 4096, 8192]

def nodfr_state(numdsts, numtrees, numecmp):
    return numdsts * numtrees * numtrees * (64 + numtrees) * numecmp

def nores_state(numdsts, numtrees, numecmp):
    return numdsts * numtrees * 64 * numecmp

def line_state(numdsts, numtrees, numecmp):
    pass

for topo in TOPOS:
    results = {'64r': {}}
    for bisec in BISECS:
        results['64r'][bisec] = {}
        for topo_size in TOPO_SIZES:
            results['64r'][bisec][topo_size] = {}

            # Get the topology file
            topof = glob.glob('../topo/' + bisec + '/%s.%s.%s.%sh.yaml' % (topo, bisec, '64r', topo_size))[0]

            # Get the number of switches
            out = subprocess.check_output('grep -- \'- switch\' ' + topof + ' | wc -l', shell=True)
            num_sw = int(out)

            # Get the maximum number of switches
            """
            tablefs = glob.glob('../tree_tables/' + bisec + \
                '/tables.%s.%s.%s.%sh.edst.*.json' % (topo, bisec, '64r', topo_size))
            ttgs = map(lambda x: x.split('.')[-3], tablefs)
            ttgs = filter(lambda x: x.find('-') >= 0, ttgs)
            ttgs = map(lambda x: int(x.split('-')[-1]), ttgs)

            # I could instead find the number of layers by calling ../tree_alg.py
            # If I need to, I will.  Looks like I should. w/e for now.
            if len(ttgs) == 0:
                continue
            """

            # Finally get the number of layers
            #num_layers = max(ttgs)
            #layer_sizes = [max(ttgs)] + [x for x in (4, 6, 8) if x < max(ttgs)]
            layer_sizes = [20] + [x for x in (4, 6, 8)]
            for num_layers in layer_sizes:

                for ttg, ttg_func in (('nodfr', nodfr_state), ('nores', nores_state)):
                    ttg_key = '%s-%dres' % (ttg, num_layers)
                    results['64r'][bisec][topo_size][ttg_key] = {}
                    results['64r'][bisec][topo_size][ttg_key]['sw_tcam_bits'] = \
                        ttg_func(num_sw, num_layers, 8)
                    results['64r'][bisec][topo_size][ttg_key]['host_tcam_bits'] = \
                        ttg_func(topo_size, num_layers, 8)


    print topo
    print yaml.dump(results)
