#!/usr/bin/python

import argparse
import numpy
import os
import scipy.stats
import sys
import traceback
import yaml

def get_sim_info(fname):
    if fname.rfind('/') < 0:
        sys.stderr.write('ERROR: Unable to find bisection be cause of a lack of \'/\'')
        sys.exit(1)
    split_fname = fname.split('/')
    bisec = split_fname[-2]
    simname = split_fname[-1]
    split_name = simname.split('.')
    if len(split_name) == 14:
        fail_output, topo, abisec, radix, hosts, model, ttg, degree, fmodel, \
            fails, ecmp, corr, run, yaml = split_name
        num_trees = 'max'
        maxl1 = 'max'
        num_trees_str = 'max-t-max'
    elif len(split_name) == 15:
        fail_output, topo, abisec, radix, hosts, model, ttg, num_trees_str, degree, fmodel, \
            fails, ecmp, corr, run, yaml = split_name
    else:
        print split_name
        raise ValueError ('Unexpected split_name length: %d' % len(split_name))

    # Some checking
    if fail_output != 'fail_output':
        raise ValueError ('Tree fail sim results must start with \'fail_output\'')
    if bisec != abisec:
        raise ValueError ('Inconsistent bisection bandwidths: %s and %s' % (bisec, abisec))
    if run != '1':
        raise ValueError ('Multiple runs are not yet supported')

    hosts = int(hosts[:hosts.find('h')])
    fails = int(fails[:fails.find('f')])

    return topo, bisec, radix, hosts, model, ttg, num_trees_str, degree, fmodel, \
        fails, ecmp, corr, run

def parse_files(args):
    fnames = args.files

    data = {}
    stretch_fields = ['median_fstretch', '99p_fstretch', '99.9p_fstretch',
        '99.99p_fstretch', '99.999p_fstretch', 'max_fstretch',
        'median_stretch', '99p_stretch', '99.9p_stretch', '99.99p_stretch',
        '99.999p_stretch', 'max_stretch']
    stretch_data = {}
    t_topo, t_bisec, t_radix, t_hosts, t_model, t_ttg, t_num_trees, t_degree, t_fmodel, \
        t_fails, t_ecmp, t_corr, t_run = get_sim_info(fnames[0])
    for fname in fnames:

        topo, bisec, radix, hosts, model, ttg, num_trees, degree, fmodel, \
            fails, ecmp, corr, run = get_sim_info(fname)

        # Sanity checking the files that we are parsing
        if topo != t_topo:
            sys.stderr.write('ERROR: Mixing results of differing topologies\n')
            return
        if bisec != t_bisec:
            sys.stderr.write('ERROR: Mixing results of differing bisection bandwidths\n')
            return
        if degree != t_degree:
            sys.stderr.write('ERROR: Mixing results of differing degrees\n')
            return
        if fmodel != t_fmodel:
            sys.stderr.write('ERROR: Mixing results of differing failure models\n')
            return

        #XXX: I could do this somewhere else. Whatever.
        ttg = ttg + '.' + num_trees

        # Create room in the dictionary
        if hosts not in data:
            data[hosts] = {}
            stretch_data[hosts] = {}
        if model not in data[hosts]:
            data[hosts][model] = {}
            stretch_data[hosts][model] = {}
        if ttg not in data[hosts][model]:
            data[hosts][model][ttg] = {}
            stretch_data[hosts][model][ttg] = {}
        if ecmp not in data[hosts][model][ttg]:
            data[hosts][model][ttg][ecmp] = {}
            stretch_data[hosts][model][ttg][ecmp] = {}
        if corr not in data[hosts][model][ttg][ecmp]:
            data[hosts][model][ttg][ecmp][corr] = {}
            stretch_data[hosts][model][ttg][ecmp][corr] = {}
            if args.results == 'fail':
                data[hosts][model][ttg][ecmp][corr]['short_avg'] = {}
                data[hosts][model][ttg][ecmp][corr]['short_99'] = {}
                data[hosts][model][ttg][ecmp][corr]['short_max'] = {}
                data[hosts][model][ttg][ecmp][corr]['table_avg'] = {}
                data[hosts][model][ttg][ecmp][corr]['table_99'] = {}
                data[hosts][model][ttg][ecmp][corr]['table_max'] = {}
                stretch_data[hosts][model][ttg][ecmp][corr] = \
                    {stretch_field: {} for stretch_field in stretch_fields}
            else:
                data[hosts][model][ttg][ecmp][corr]['short_avg_tput'] = {}
                data[hosts][model][ttg][ecmp][corr]['table_avg_tput'] = {}

        with open(fname) as f:
            try:
                results = yaml.load(f)

                # Get failure percent avgs
                if args.results == 'fail':
                    short_avg = 1.0 * results['failed_short_flows'] / results['tot_flows']
                    table_avg = 1.0 * results['failed_table_flows'] / results['tot_flows']
                    data[hosts][model][ttg][ecmp][corr]['short_avg'][fails] = short_avg
                    data[hosts][model][ttg][ecmp][corr]['table_avg'][fails] = table_avg

                    short_fail_runs = map(lambda e: 1.0 * e[0] / e[1], results['fail_runs_short'])
                    table_fail_runs = map(lambda e: 1.0 * e[0] / e[1], results['fail_runs_table'])
                    data[hosts][model][ttg][ecmp][corr]['short_99'][fails] = \
                        numpy.asscalar(scipy.stats.scoreatpercentile(short_fail_runs, 99))
                    data[hosts][model][ttg][ecmp][corr]['table_99'][fails] = \
                        numpy.asscalar(scipy.stats.scoreatpercentile(table_fail_runs, 99))
                    data[hosts][model][ttg][ecmp][corr]['short_max'][fails] = \
                        max(short_fail_runs)
                    data[hosts][model][ttg][ecmp][corr]['table_max'][fails] = \
                        max(table_fail_runs)

                    # Generate the CDF, if requested
                    if args.cdf:
                        cdf_fname = 'cdf.' + bisec + '.' + fname.split('/')[-1]
                        if os.path.exists(cdf_fname):
                            sys.stderr.write('ERROR: %s already exists!\n' % cdf_fname)
                            sys.exit(1)
                        else:    
                            cdf_f = open(cdf_fname, 'w')
                            yaml.dump(table_fail_runs, cdf_f)

                    # Get stretch data
                    for stretch_field in stretch_fields:
                        if stretch_field in results:
                            #nkey = stretch_field.split('_')[0]
                            nkey = stretch_field
                            stretch_data[hosts][model][ttg][ecmp][corr][nkey][fails] = \
                                results[stretch_field]
                else:
                    data[hosts][model][ttg][ecmp][corr]['short_avg_tput'][fails] = results['short_avg_tput']
                    data[hosts][model][ttg][ecmp][corr]['table_avg_tput'][fails] = results['table_avg_tput']
            except KeyboardInterrupt:
                raise
            except:
                traceback.print_exc(file=sys.stderr)
                tables = {}
                print '%s cannot be parsed' % fname
                #raise

    if args.cdf:
        return

    #print 'DATA:'
    #yaml.dump(data, sys.stdout)
    #print 'STRETCH DATA:'
    #yaml.dump(stretch_data, sys.stdout)

    if args.prefix:
        prefix = args.prefix + '.'
    else:
        prefix = ''

    # Open up a file with the right ts
    if args.results == 'fail':
        outfname = 'prob_fail.%s%s.%s.%s.%s.yaml' % (prefix, topo, bisec, degree, fmodel)
    else:
        outfname = 'tput.%s%s.%s.%s.%s.yaml' % (prefix, topo, bisec, degree, fmodel)
    if os.path.exists(outfname):
        sys.stderr.write('ERROR: %s already exists!\n' % outfname)
    else:    
        outf = open(outfname, 'w')
        yaml.dump(data, outf)

    if args.results == 'fail':
        stretch_outfname = 'stretch_fail.%s%s.%s.%s.%s.yaml' % (prefix, topo, bisec, degree, fmodel)
        if os.path.exists(stretch_outfname):
            sys.stderr.write('ERROR: %s already exists!\n' % stretch_outfname)
        else:    
            stretch_f = open(stretch_outfname, 'w')
            yaml.dump(stretch_data, stretch_f)

def main():
    # Create the parser and subparsers
    parser = argparse.ArgumentParser(
        description='Parse the output files of failure data.')

    # The files to parse
    parser.add_argument('files', nargs='+', \
        help='The output files')

    # Optionally write the state to the chosen filename
    parser.add_argument('-p', '--prefix',
        help='A prefix to add to the resulting output files.')
        
    # Get throughput instead of failure data
    parser.add_argument('--results', default='fail',
        choices=('fail', 'tput'),
        help='Get either failure or throughput data')

    parser.add_argument('--cdf', action='store_true',
        help='Only write out a CDF of the failure data')

    args = parser.parse_args()
    parse_files(args)

if __name__ == "__main__":
    main()
