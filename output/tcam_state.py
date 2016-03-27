#!/usr/bin/python

import argparse
import os
import sys
import time
import traceback
import yaml

def get_ts(ts_str):
    try:
        time.strptime(ts_str, '%Y-%m-%d-%H:%M:%S')
        ts = ts_str
    except:
        ts = time.strftime('%F-%T')
    return ts

def get_sim_info(fname):
    if fname.rfind('/') >= 0:
        simname = fname[fname.rfind('/')+1:]
    else:
        simname = fname
    split_name = simname.split('.')
    topo, bisec, radix, hosts, fail, failtype, model, srchbh, u2, u3 = split_name[:10]
    hosts = int(hosts[:hosts.find('h')])
    return topo, bisec, radix, hosts, fail, failtype, model, srchbh

def parse_files(fnames):
    data = {}
    state = {}
    t_topo, t_bisec, t_radix, t_hosts, t_fail, t_failtype, t_model, t_srchbh = get_sim_info(fnames[0])
    for fname in fnames:
        topo, bisec, radix, hosts, fail, failtype, model, srchbh = get_sim_info(fname)

        # Sanity checking the files that we are parsing
        if topo != t_topo:
            sys.stderr.write('ERROR: Mixing results of differing topologies\n')
            return
        if bisec != t_bisec:
            sys.stderr.write('ERROR: Mixing results of differing bisection bandwidths\n')
            return
        if failtype != t_failtype:
            sys.stderr.write('ERROR: Mixing results of differing failtype\n')
            return

        #switches, sw_tables, tables, wildtables, hosts_tables, stretch = set(), {}, {}, {}, {}, {}
        #state['max_entry_bytes'] = 0

        if radix not in data:
            data[radix] = {}
        if hosts not in data[radix]:
            data[radix][hosts] = {}
        if fail not in data[radix][hosts]:
            data[radix][hosts][fail] = {}
        if model not in data[radix][hosts][fail]:
            data[radix][hosts][fail][model] = {}
        if srchbh not in data[radix][hosts][fail][model]:
            data[radix][hosts][fail][model][srchbh] = {}

        with open(fname) as f:
            try:
                results = yaml.load(f)
                
                # Find the keys to look for based on the model
                keys = []
                if model == 'plinko' or model == 'plinko-c' or model == 'plinko-nc':
                    keys = ['host_dst_bits', 'hosts_tcam', 'max_rp_bytes',
                        'avg_rp_bytes', 'avg_rp_unpacked_bytes', 'port_bits',
                        'sw_dst_bits', 'sw_tcam', 'sw_tcam_unpacked']
                elif model == 'mpls-frr':
                    keys = ['cam', 'host_dst_bits', 'hosts_cam',
                        'label_bits', 'port_bits', 'sw_dst_bits']
                elif model == 'eth-fcp':
                    keys = ['cam', 'host_dst_bits', 'hosts_cam',
                        'label_bits', 'port_bits', 'sw_dst_bits']
                else:
                    raise ValueError('Unknown model: %s' % model)

                maxes = {}
                #print
                #print model, srchbh
                for sw in results:
                    if model == 'plinko':
                        if results[sw]['sw_tcam'] > 0:
                            #assert(1.0 * results[sw]['hosts_tcam'] / results[sw]['sw_tcam'] <= 18)
                            pass
                            #print 'hosts per sw:', 1.0 * results[sw]['hosts_tcam'] / results[sw]['sw_tcam']
                    else:
                        if results[sw]['cam'] > 0:
                            pass
                            #print 'hosts per sw:', 1.0 * results[sw]['hosts_cam'] / results[sw]['cam']
                    for key in keys:
                        if key not in maxes:
                            maxes[key] = 0
                        maxes[key] = max(maxes[key], results[sw][key])
                data[radix][hosts][fail][model][srchbh] = maxes
            except KeyboardInterrupt:
                raise
            except:
                traceback.print_exc(file=sys.stderr)
                tables = {}
                print '%s cannot be parsed' % fname
                #raise

    """
        for sw in sw_tables:
            if sw_tables[sw] != switches:
                tables = {}
                print '%s is incomplete!' % fname
                break
        #for sw, tcamsize in tables.iteritems():
        #    print '%s: %d' % (sw, tcamsize)
        if len(tables) > 0:
            maxtable = max(tables.values())
            data[radix][fail][hosts] = {}
            data[radix][fail][hosts]['maxtable'] = maxtable
            data[radix][fail][hosts]['maxbytes'] = state['max_entry_bytes']
            data[radix][fail][hosts]['wildtable'] = max(wildtables.values())
            data[radix][fail][hosts]['hosts_table'] = max(hosts_tables.values())
            #data[radix][fail][hosts]['tables'] = tables
            stretch_data[radix][fail][hosts] = stretch
        else:
            print '%s is empty!' % fname
    for radix in data:
        for fail in data[radix]:
            stats = data[radix][fail]
            numhosts = stats.keys()
            numhosts.sort()
            tcam_sizes = [stats[num]['maxtable'] for num in numhosts]
            wildtable_sizes = [stats[num]['wildtable'] for num in numhosts]
            hosts_table_sizes = [stats[num]['hosts_table'] for num in numhosts]
            entry_bytes = [stats[num]['maxbytes'] for num in numhosts]
            data[radix][fail] = {'numhosts':numhosts, 'tcam_sizes':tcam_sizes, 'entry_bytes':entry_bytes}
            data[radix][fail]['wildtable_sizes'] = wildtable_sizes
            data[radix][fail]['hosts_table_sizes'] = hosts_table_sizes
            #data[radix][fail]['tables'] = {}
            #for num in numhosts:
            #    data[radix][fail]['tables'][num] = stats[num]['tables']
    """

    # Open up a file with the right ts
    outfname = 'tcam_sizes.%s.%s.%s.yaml' % (topo, bisec, failtype)
    if os.path.exists(outfname):
        sys.stderr.write('ERROR: %s already exists!\n' % outfname)
    else:    
        outf = open(outfname, 'w')
        yaml.dump(data, outf)
        outf.close()

def main():
    # Create the parser and subparsers
    parser = argparse.ArgumentParser(
        description='Parse the output files for TCAM state.')

    # The files to parse
    parser.add_argument('files', nargs='+', \
        help='The output files')

    args = parser.parse_args()

    parse_files(args.files)

if __name__ == "__main__":
    main()
