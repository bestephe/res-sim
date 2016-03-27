#!/usr/bin/python

import argparse
import itertools
import numpy as np
from pylab import *
import matplotlib.cm as mplcm
import matplotlib.colors as mplcolors
import os
import sys
import yaml

params = {#'text.usetex': True,
    #'font.size' : 16,
    #'axes.labelsize': 16,
    #'text.fontsize' : 16,
    #'xtick.labelsize' : 16,
    #'ytick.labelsize' : 16,
    'legend.fontsize' : 'medium',
    #'legend.fontsize' : '14',
    'lines.linewidth' : 3,
    'lines.markersize' : 8
}
rcParams.update(params)

#master_linestyles = ['-', '--', '-.', ':']
master_linestyles = [ '-.', ':', '--', '-',]

def radix2label(radix):
    numports = int(radix[:radix.find('r')])
    return '%d Ports' % numports
def res2label(res):
    r = int(res[:res.find('res')])
    if res.find('exp') < 0:
        return '%d-R' % r
    else:
        return '%d-R (M)' % r
def hosts2label(hosts):
    h = int(hosts[:hosts.find('h')])
    if hosts.find('exp') < 0:
        return '%d-H' % h
    else:
        return '%d-H (M)' % h
def res2label(res):
    r = int(res[:res.find('res')])
    if res.find('exp') < 0:
        return '%d-R' % r 
    else:
        return '%d-R (M)' % r
def key2label(key):
    return 'Hosts: %s, Model: %s, ECMP: %s, CORR: %s, %s' % key

def gen_results(data, ptype):
    results = {}

    for hosts in data:
        for model in data[hosts]:
            for res in data[hosts][model]:
                for ecmp in data[hosts][model][res]:
                    for corr in data[hosts][model][res][ecmp]:
                        for table_type in ['table_99', 'table_avg']:
                            if table_type not in data[hosts][model][res][ecmp][corr]:
                                continue

                            if ptype == 'res':
                                key = (hosts, model, ecmp, corr, table_type)
                                line_name = res
                            else:
                                key = (res, model, ecmp, corr, table_type)
                                line_name = hosts

                            if key not in results:
                                results[key] = {}

                            xs = data[hosts][model][res][ecmp][corr][table_type].keys()
                            xs.sort()
                            ys = [data[hosts][model][res][ecmp][corr][table_type][x] for x in xs]
                            results[key][line_name] = (xs, ys)
                            print line_name, xs, ys

    return results

def plot_tcam_sizes(args, results):
    basename = '.'.join(args.fname.split('.')[:-1])

    for key in results:

        # Get and Sort the lines:
        lines = results[key].items()
        if args.ptype == 'res':
            sort_func = lambda x, y: cmp(x[0], y[0])
        else:
            def hosts_sort(x, y):
                xs, ys = x[0], y[0]
                order = ['256h_exp', '256h', '512h_exp',
                    '512h', '1024h_exp', '1024h', '2048h', '2048h_exp'] 
                return cmp(order.index(xs), order.index(ys))
            sort_func = hosts_sort
        lines.sort(sort_func)

        # Setup the figure
        f = figure(figsize=(8, 3))
        if len(lines) > 4 and args.ptype == 'hosts':
            f.subplots_adjust(hspace=0.15, wspace=0.185, bottom=0.4)
            legend_bbox = (0.5, -0.8)
            legend_width = 4
        else:
            f.subplots_adjust(hspace=0.15, wspace=0.185, bottom=0.32)
            legend_bbox = (0.5, -0.52)
            legend_width = 8

        # Build the colormap
        color_map = get_cmap('Dark2')
        c_norm = mplcolors.Normalize(vmin=0, vmax=len(lines)-1)
        scalar_map = mplcm.ScalarMappable(norm=c_norm, cmap=color_map)
        linescycle = itertools.cycle(master_linestyles)

        ax = gca()
        ax.set_color_cycle([scalar_map.to_rgba(i) for i in \
            xrange(len(lines))])

        # Plot the data
        for line, (xs, ys) in lines:
            print line, xs, ys
            if args.ptype == 'res':
                label = res2label(line)
            else:
                label = hosts2label(line)
            plot(xs, ys, label=label,
                linestyle=next(linescycle))

        grid(True, axis='y')
        ax.set_xscale('log', basex=2)
        #xlim(100, 2048)
        ax.set_yscale('log', basex=10)
        #ylim(0.000001, 0.5)
        ax.set_xlabel('Number of Failures')
        ax.set_ylabel('Fraction of Flows Failed')

        title(key2label(key))

        # Add legend
        ax.legend(loc='lower center', bbox_to_anchor=legend_bbox, ncol=legend_width, columnspacing=0.5, handletextpad=0.25, fancybox=True, shadow=True)

        #ticks = ax.get_xticks()
        #labels = map(lambda x: (str(int(x/1000)) + 'K'), ticks)
        #ax.set_xticklabels(labels)

        savename = basename + '.'.join(key) + '.pdf'
        print savename
        savefig(savename)


def main():
    # Create the parser and subparsers
    parser = argparse.ArgumentParser(
        description='Plot the output files of failure data.')

    # Vary resilience of hosts
    parser.add_argument('--ptype', default='res',
        choices=('res', 'hosts'),
        help='Varied either resilience of number of hosts')

    # The files to parse
    parser.add_argument('fname', nargs=1, \
        help='The output files')

    # Parse the arguments
    args = parser.parse_args()
    args.fname = args.fname[0]

    data = yaml.load(open(args.fname))
    results = gen_results(data, args.ptype)
    plot_tcam_sizes(args, results)
    show()

if __name__ == "__main__":
    main()
