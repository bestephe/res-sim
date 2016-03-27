#!/usr/bin/python

import sys
import yaml
from pylab import *

params = {'text.usetex': True
}
rcParams.update(params)

master_colors = [
    (1, 1, 1),
    (0.31, 0.505, 0.741),
    (0.968, 0.588, 0.275),
    (0.22, 0.549, 0.235),
    (0.549, 0.224, 0.22),
    (0.741, 0.31, 0.325)
]
master_linestyles = ['-', '--', '-.', ':', '-', '--', '-.', ':']

def radix2label(radix):
    numports = int(radix[:radix.find('r')])
    return '%d Ports' % numports
def fail2label(fail):
    f = int(fail[:fail.find('f')])
    return '%d-R ' % f

def plot_tcam_sizes(results):
    for radix in results:
        figure()
        colors = master_colors[:]
        linestyles = master_linestyles[:]

        # Sort the fails numerically
        fails = results[radix].keys()
        fails = map(lambda f: int(f[:f.find('f')]), fails)
        fails.sort()
        fails = map(lambda f: '%df' % f, fails)
        for fail in fails:
            numhosts = results[radix][fail]['numhosts']
            tcam_sizes = results[radix][fail]['tcam_sizes']
            #plot(numhosts, tcam_sizes, linestyles.pop(0), colors.pop(0), label=fail)
            plot(numhosts, tcam_sizes, label=fail2label(fail))
        grid(True, axis='both')
        gca().set_xscale('log', basex=2)
        #xlim(100, 2048)
        #ylim(0, 1500)
        xlabel('Number of Hosts')
        ylabel('Maximum TCAM Entries')
        legend(loc='upper left')
        savename = radix + '.pdf'
        savefig(savename)

def main():
    if len(sys.argv) != 2:
        print 'Usage: %s <fname>' % sys.argv[0]
        sys.exit(1)
    results = yaml.load(open(sys.argv[1]))
    plot_tcam_sizes(results)
    show()

if __name__ == "__main__":
    main()
