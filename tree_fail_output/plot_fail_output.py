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
    'font.size' : 16,
    'axes.labelsize': 16,
    'text.fontsize' : 16,
    'xtick.labelsize' : 16,
    'ytick.labelsize' : 16,
    #'legend.fontsize' : 'medium',
    'legend.fontsize' : '13',
    'lines.linewidth' : 5,
    'lines.markersize' : 8
}
rcParams.update(params)

master_linestyles = ['-', '--', '-.', ':']
#master_linestyles = [ '-.', ':', '--', '-',]
master_markers = ['o', 'D', 'v', '^', '<', '>', '8', 's', 'p', '*', '+', 'x']

def radix2label(radix):
    numports = int(radix[:radix.find('r')])
    return '%d Ports' % numports

def key2label(key):
    return key

def line2label(line):
    #return line
    if line == 'shortest':
        return line
    else:
        return line.split('.')[0] + ' ' + line.split('-')[-1]

def line2ls(line):
    #print line
    if line.find('alayer') >= 0:
        ls = '--'
    elif line.find('mlayer') >= 0:
        ls = '-.'
    elif line.find('T') >= 0:
        ls = ':'
    else:
        ls = '-'
    return ls

def gen_prob_results(data, args):
    results = {}

    for hosts in data:
        for model in data[hosts]:
            for ttg in data[hosts][model]:
                for ecmp in data[hosts][model][ttg]:
                    for corr in data[hosts][model][ttg][ecmp]:
                        for base_type in ['99', 'avg']:
                            if args.shortest:
                                table_types = ['short_', 'table_']
                            else:
                                table_types = ['table_']
                            for table_type in table_types:
                                full_type = table_type + base_type
                                if full_type not in data[hosts][model][ttg][ecmp][corr]:
                                    print 'continuing....'
                                    continue

                                # Get the failures and throughputs 
                                fails = data[hosts][model][ttg][ecmp][corr][full_type].keys()
                                fails.sort()
                                prob_fails = [data[hosts][model][ttg][ecmp][corr][full_type][x] for x in fails]

                                # Normalize throughputs
                                numhosts = hosts
                                assert (type(numhosts) == type(1))
                                prob_fails = map(lambda x: 1.0 * x / numhosts, prob_fails)

                                # Get the line names
                                if table_type == 'short_':
                                    line_name = 'shortest'
                                else:
                                    line_name = ttg
                                
                                if args.ptype == 'fails':
                                    # Create the keys and line names
                                    key = ('%dh' % hosts, model, ecmp, corr, base_type)

                                    # Add the key to the results
                                    if key not in results:
                                        results[key] = {}

                                    # This case is simpler.  Just save the fails/prob_fails
                                    results[key][line_name] = [fails, prob_fails]
                                    print line_name, fails, prob_fails

                                elif args.ptype == 'hosts':
                                    # Some data re-arranging to be done here
                                    for i, fail in enumerate(fails):
                                        key = ('%df' % fail, model, ecmp, corr, base_type)

                                        # Add the key to the results
                                        if key not in results:
                                            results[key] = {}

                                        # Add the line name to the results
                                        if line_name not in results[key]:
                                            results[key][line_name] = [[], []]

                                        # Accumulate our results
                                        if hosts not in results[key][line_name][0]:
                                            results[key][line_name][0].append(hosts)
                                            results[key][line_name][1].append(prob_fails[i])
                                else:
                                    raise ValueError('Unkown ptype %s' % args.ptype)

    #print yaml.dump(results)
    #sys.exit(1)

    return results

def gen_tput_results(data, args):
    results = {}

    for hosts in data:
        for model in data[hosts]:
            for ttg in data[hosts][model]:
                for ecmp in data[hosts][model][ttg]:
                    for corr in data[hosts][model][ttg][ecmp]:
                        if args.shortest:
                            table_types = ['short_avg_tput', 'table_avg_tput']
                        else:
                            table_types = ['table_avg_tput']
                        for table_type in table_types:
                            if table_type not in data[hosts][model][ttg][ecmp][corr]:
                                continue

                            # Get the failures and throughputs 
                            fails = data[hosts][model][ttg][ecmp][corr][table_type].keys()
                            fails.sort()
                            tputs = [data[hosts][model][ttg][ecmp][corr][table_type][x] for x in fails]

                            # Normalize throughputs
                            numhosts = hosts
                            assert (type(numhosts) == type(1))
                            tputs = map(lambda x: 1.0 * x / numhosts, tputs)

                            # Get the line names
                            if table_type == 'short_avg_tput':
                                line_name = 'shortest'
                            else:
                                line_name = ttg
                            
                            if args.ptype == 'fails':
                                # Create the keys and line names
                                key = ('%dh' % hosts, model, ecmp, corr)

                                # Add the key to the results
                                if key not in results:
                                    results[key] = {}

                                # This case is simpler.  Just save the fails/tputs
                                results[key][line_name] = [fails, tputs]
                                print line_name, fails, tputs

                            elif args.ptype == 'hosts':
                                # Some data re-arranging to be done here
                                for i, fail in enumerate(fails):
                                    key = ('%df' % fail, model, ecmp, corr)

                                    # Add the key to the results
                                    if key not in results:
                                        results[key] = {}

                                    # Add the line name to the results
                                    if line_name not in results[key]:
                                        results[key][line_name] = [[], []]

                                    # Accumulate our results
                                    results[key][line_name][0].append(hosts)
                                    results[key][line_name][1].append(tputs[i])
                            else:
                                raise ValueError('Unkown ptype %s' % args.ptype)

    return results

def compute_tput_reduction(results):
    for key in results:
        print 'key:', key
        shortest = 'shortest'
        shortest_xs, shortest_ys = results[key][shortest]
        lines = results[key].items()
        for line, (xs, ys) in lines:
            #print xs, exp_xs
            common_xs = list(set(shortest_xs) & set(xs))
            common_xs.sort()
            if len(common_xs) > 0:
                new_ys = [ys[xs.index(common_x)] for common_x in common_xs]
                new_shortest_ys = [shortest_ys[shortest_xs.index(common_x)] for common_x in common_xs]
                reduct = map(lambda y: 1.0 - (1.0 * y[0] / y[1]), zip(new_ys, new_shortest_ys))
                print line, common_xs, reduct
        print

def plot_tcam_sizes(args, results):
    basename = '-'.join(args.fname.split('.')[:-1])

    keys = results.keys()
    keys.sort()
    for key in keys:

        # Get and Sort the lines:
        lines = results[key].items()
        def line_sort(x, y):
            xl, (xx, xy) = x
            yl, (yx, yy) = y
            common_x = list(set(xx) & set(yx))
            common_x.sort()
            if len(common_x) > 0:
                return cmp(yy[yx.index(common_x[-1])], xy[xx.index(common_x[-1])])
            else:
                return cmp(yl, xl)
        lines.sort(line_sort)

        # Setup the figure
        f = figure(figsize=(7, 6))
        f.subplots_adjust(hspace=0.15, wspace=0.185, left=0.2, bottom=0.43)
        legend_bbox = (0.43, -0.9)
        legend_width = 4

        # Build the colormap
        color_map = get_cmap('Set1')
        c_norm = mplcolors.Normalize(vmin=0, vmax=len(lines)*2)
        scalar_map = mplcm.ScalarMappable(norm=c_norm, cmap=color_map)
        linescycle = itertools.cycle(master_linestyles)
        markercycle = itertools.cycle(master_markers)

        ax = gca()
        ax.set_color_cycle([scalar_map.to_rgba(i) for i in \
            xrange(len(lines))])

        # Plot the data
        for line, (xs, ys) in lines:
            #XXX: 4-t is low resilience
            if line.find('4-t') >= 0:
                continue
            #XXX: Only 8-t for now
            if line.find('8-t') < 0:
                continue

            #print line, xs, ys
            label = line2label(line)
            ls = line2ls(line)
            if max(ys) <= 0:
                print 'Ignoring label \'%s\' because it never saw failures!' % label
                plot([], [], label=label, linestyle=ls, marker=next(markercycle))
            else:
                plot(xs, ys, label=label, linestyle=ls, marker=next(markercycle))
            #print label, xs, ys

        grid(True, axis='y')
        ax.set_xscale('log', basex=2)
        if args.fname.find('tput') >= 0:
            #xlim(100, 2048)
            #ax.set_yscale('log', basex=10)
            #ylim(0.000001, 0.5)
            pass
        elif args.fname.find('prob_fail') >= 0:
            ax.set_yscale('log', basex=10)
            #ylim(0.000001, 0.5)
        else:
            raise ValueError


        if args.ptype == 'fails':
            ax.set_xlabel('Number of Failures')
        elif args.ptype == 'hosts':
            ax.set_xlabel('Number of Hosts')
        else:
            raise ValueError

        if args.fname.find('tput') >= 0:
            ax.set_ylabel('Normalized\nThroughput')
        elif args.fname.find('prob_fail') >= 0:
            ax.set_ylabel('Fraction of\nFlows Failed')
        else:
            raise ValueError

        title(key2label(key))

        # Add legend
        ax.legend(loc='lower center', bbox_to_anchor=legend_bbox, ncol=legend_width, columnspacing=0.5, handletextpad=0.25, fancybox=True, shadow=True)

        #ticks = ax.get_xticks()
        #labels = map(lambda x: (str(int(x/1000)) + 'K'), ticks)
        #ax.set_xticklabels(labels)

        savename = basename + '-' + '-'.join(key) + '.pdf'
        #print savename
        savefig(savename)


def main():
    # Create the parser and subparsers
    parser = argparse.ArgumentParser(
        description='Plot the output files of failure data.')

    # Vary resilience of hosts
    parser.add_argument('--ptype', default='fails',
        choices=('fails', 'hosts'),
        help='Vary on the x-axis either the number of failures or the ' \
            'number of hosts')

    # Vary resilience of hosts
    parser.add_argument('--shortest', action='store_true',
        help='Plot the shortest tables as well')

    # The files to parse
    parser.add_argument('fname', nargs=1, \
        help='The output files')

    # Parse the arguments
    args = parser.parse_args()
    args.fname = args.fname[0]

    # Parse the data
    data = yaml.load(open(args.fname))
    if args.fname.find('tput') >= 0:
        results = gen_tput_results(data, args)
    elif args.fname.find('prob_fail') >= 0:
        results = gen_prob_results(data, args)
    else:
        raise ValueError

    # Compute % reduction in throughput verses shortest
    if args.shortest and args.fname.find('tput') >= 0:
        compute_tput_reduction(results)

    # Do the plotting
    plot_tcam_sizes(args, results)
    show()

if __name__ == "__main__":
    main()
