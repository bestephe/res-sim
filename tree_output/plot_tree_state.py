#!/usr/bin/python
import itertools
import math
import numpy as np
from pylab import *
import matplotlib.cm as mplcm
import matplotlib.colors as mplcolors
import os
import sys
import yaml

SMALL = False

params = {#'text.usetex': True,
    'font.size' : 16,
    'axes.labelsize': 16,
    'text.fontsize' : 16,
    'xtick.labelsize' : 16,
    'ytick.labelsize' : 16,
    #'legend.fontsize' : 'medium',
    'legend.fontsize' : '13',
    'lines.linewidth' : 3,
    'lines.markersize' : 8
}

small_params = {#'text.usetex': True,
    'font.size' : 20,
    'axes.labelsize': 20,
    'text.fontsize' : 20,
    'xtick.labelsize' : 20,
    'ytick.labelsize' : 20,
    #'legend.fontsize' : 'medium',
    'legend.fontsize' : '20',
    'lines.linewidth' : 4,
    'lines.markersize' : 8
}

# Determine which parameter set we would like to use
if SMALL:
    rcParams.update(small_params)
else:
    rcParams.update(params)

master_linestyles = ['-', '--', '-.', ':']

def line2label(line):
    return line

def line2ls(line):
    print line
    if line.find('alayer') >= 0:
        ls = '--'
    elif line.find('mlayer') >= 0:
        ls = '-.'
    elif line.find('T') >= 0:
        ls = ':'
    else:
        ls = '-'
    return ls

def gen_results(data):
    results = {}

    for radix in data:
        assert(64 == int(radix[:radix.find('r')]))
        for bisec in data[radix]:
            results[bisec] = {}
            for hosts in data[radix][bisec]:
                for model in data[radix][bisec][hosts]:
                    print model
                    if len(data[radix][bisec][hosts][model]) == 0:
                        continue
                    
                    # Assign the line name
                    linename = model

                    # If we're plotting in this way, any ttg with *-1 or *-non2power
                    # should be ignored
                    if model.find('-') >= 0:
                        l1width = int(model.split('-')[-1])
                        logwidth = math.log(l1width, 2)
                        if l1width == 1 or not logwidth.is_integer():
                            continue

                    for num_trees in data[radix][bisec][hosts][model]:
                        if num_trees not in results[bisec]:
                            results[bisec][num_trees] = {'host_tcam_bits': {}, 'sw_tcam_bits': {}}

                        if linename not in results[bisec][num_trees]['host_tcam_bits']:
                            results[bisec][num_trees]['host_tcam_bits'][linename] = {}
                            results[bisec][num_trees]['sw_tcam_bits'][linename] = {}

                        for host_sw in ('host_tcam_bits', 'sw_tcam_bits'):
                            results[bisec][num_trees][host_sw][linename][hosts] = \
                                data[radix][bisec][hosts][model][num_trees][host_sw] * 8 # 8-way ECMP

    # Actually create the lines
    fix_results = {}
    for bisec in results:
        for num_trees in results[bisec]:
            for host_sw in results[bisec][num_trees]:
                fig = bisec + '-' + num_trees + '-' + host_sw
                for linename in results[bisec][num_trees][host_sw]:
                    hosts = results[bisec][num_trees][host_sw][linename].keys()
                    hosts.sort()
                    states = [results[bisec][num_trees][host_sw][linename][h] / 100.0 for h in hosts]

                    if fig not in fix_results:
                        fix_results[fig] = {}
                    fix_results[fig][linename] = (hosts, states)

    print yaml.dump(fix_results)

    return fix_results

def plot_tcam_sizes(fname, results):
    basename = '-'.join(fname.split('.')[:-1])
    
    for key in results:

        # Get and Sort the lines:
        lines = results[key].items()
        def line_sort(x, y):
            xl, (xh, xs) = x
            yl, (yh, ys) = y
            print xl, ':', xh
            print yl, ':', yh
            common_h = list(set(xh) & set(yh))
            common_h.sort()
            print 'common_h:', common_h
            if len(common_h) > 0:
                return cmp(ys[yh.index(common_h[-1])], xs[xh.index(common_h[-1])])
            else:
                return cmp(yl, xl)
        lines.sort(line_sort)

        print 'lines:'
        for line in lines:
            print line
        print

        # Setup the figure
        if SMALL:
            f = figure(figsize=(6, 4.3))
        else:
            f = figure(figsize=(8, 3.75))
        #if len(lines) > 10:
        if SMALL:
            f.subplots_adjust(hspace=0.15, wspace=0.185, left=0.14, bottom=0.4)
            legend_bbox = (0.5, -.8)
            legend_width = 4
        else:
            f.subplots_adjust(hspace=0.15, wspace=0.185, left=0.14, bottom=0.35)
            legend_bbox = (0.5, -0.6)
            legend_width = 5

        # Build the colormap
        color_map = get_cmap('Set1')
        c_norm = mplcolors.Normalize(vmin=0, vmax=len(lines)*2)
        scalar_map = mplcm.ScalarMappable(norm=c_norm, cmap=color_map)
        linescycle = itertools.cycle(master_linestyles)

        ax = gca()
        ax.set_color_cycle([scalar_map.to_rgba(i) for i in \
            xrange(len(lines))])

        # Plot the data
        for line, (xs, ys) in lines:
            label = line2label(line)
            ls = line2ls(line)
            if not (label.endswith('Plinko-old') or label.endswith('Plinko-NC')):
                plot(xs, ys, label=label,
                    linestyle=ls)

        grid(True, axis='y')
        ax.set_xscale('log', basex=2)
        #xlim(100, 2048)
        ax.set_yscale('log', basex=10)
        ylim(0, 40000)
        ax.set_xlabel('Number of Hosts')
        ax.set_ylabel('TCAM Size (Kb)')

        title(key)

        # Add legend
        ax.legend(loc='lower center', bbox_to_anchor=legend_bbox, ncol=legend_width, columnspacing=0.5, handletextpad=0.25, fancybox=True, shadow=True)

        #ticks = ax.get_xticks()
        #labels = map(lambda x: (str(int(x/1000)) + 'K'), ticks)
        #ax.set_xticklabels(labels)

        savename = basename + '-' + key + '.pdf'
        print savename
        savefig(savename)


def main():
    if len(sys.argv) != 2:
        print 'Usage: %s <fname>' % sys.argv[0]
        sys.exit(1)
    data = yaml.load(open(sys.argv[1]))
    results = gen_results(data)
    plot_tcam_sizes(sys.argv[1], results)
    show()

if __name__ == "__main__":
    main()
