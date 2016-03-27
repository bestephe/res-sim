#!/usr/bin/python

import sys
import time
import yaml

def get_ts(ts_str):
    try:
        time.strptime(ts_str, '%Y-%m-%d-%H:%M:%S')
        ts = ts_str
    except:
        ts = time.strftime('%F-%T')
    return ts

def get_sim_info(fname):
        fsp = fname.split('.')
        topo = fsp[1]
        ts_str = fsp[-2]
        ts = get_ts(ts_str)
        return topo, ts

if len(sys.argv) != 2:
    print 'usage: %s tcam_state.yaml' % sys.argv[0]
    sys.exit(1)

fails = set()
hosts = set()
missing = {}
fname = sys.argv[1]
topo, ts = get_sim_info(fname)
topo2prefix = {'egft': 'B1/egft.B1.', 'jellyfish': 'B0.2/jellyfish.B0_2.', 'rocketfuel': 'rocketfuel/rocketfuel._.'}
topodir = 'topo/' + topo2prefix[topo]
outdir = 'output/' + topo2prefix[topo]
with open(fname) as f:
    tcam_state = yaml.load(f)
    for radix, radix_data in tcam_state.iteritems():
        for numfail, numfail_data in radix_data.iteritems():
            fails.add(numfail)
            hosts.update(numfail_data['numhosts'])

    for radix, radix_data in tcam_state.iteritems():
        for numfail, numfail_data in radix_data.iteritems():
            numhosts = set(numfail_data['numhosts'])
            isec = numhosts ^ hosts
            if len(isec) > 0:
                if radix not in missing:
                    missing[radix] = {}
                if numfail not in missing[radix]:
                    missing[radix][numfail] = []
            for numhost in isec:
                missing[radix][numfail].append(numhost)

output = []
for radix, radix_data in missing.iteritems():
    for fail, fail_data in radix_data.iteritems():
        for numhost in fail_data:
            output.append('./resnet_alg.py -r ' + fail[:-1] + ' --fail edges ' + topodir + radix + '.' + str(numhost) + 'h.yaml > ' + outdir + radix + '.' + str(numhost) + 'h.' + fail + '.edges.' + ts + '.yaml')

output.sort()
for cmd in output:
    print cmd
