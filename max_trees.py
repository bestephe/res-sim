#!/usr/bin/python

import glob
import subprocess
import yaml

TOPOS = ['egft', 'jellyfish']
BISECS = ['B1', 'B2', 'B4', 'B6']
SIZES = [512, 1024, 1536, 2048, 3072, 4096]

results = {}
for topo in TOPOS:
    results[topo] = {}
    for bisec in BISECS:
        results[topo][bisec] = {}
        for size in SIZES:
            topo_strs = 'topo/%(bisec)s/%(topo)s*64r*%(size)s*' % {'bisec': bisec, 'topo': topo, 'size': size}
            instances = glob.glob(topo_strs)
            instances.sort()
            for instance in instances:
                numhosts = int(instance.split('.')[-2][:-1])
                numtrees = 0
                for i in xrange(5):
                    cmd = './tree_alg.py --model edst -m ' + instance
                    out = subprocess.check_output(cmd, shell=True)
                    numtrees = max(int(out.split(' ')[0]), numtrees)
                results[topo][bisec][numhosts] = numtrees
                print '%s %s %s: %d' % (topo, bisec, numhosts, numtrees)

print yaml.dump(results)
