#!/usr/bin/python

import argparse
import os
import sys
import time
import traceback
import yaml

def get_sim_info(fname):
    if fname.find('adst') >= 0:
        return get_sim_info_adst(fname)
    else:
        return get_sim_info_edst(fname)

def get_sim_info_adst(fname):
    if fname.rfind('/') >= 0:
        simname = fname[fname.rfind('/')+1:]
    else:
        simname = fname
    split_name = simname.split('.')

    # state.jellyfish.B1.64r.1024h.adst.8-t.1.json
    # state.jellyfish.B6.64r.512h.adst.nodfr.2-t-1d.1.json
    if len(split_name) == 10:
        state, topo, bisec, radix, hosts, model, nodfr, num_trees, run, json = split_name
    else:
        print split_name
        raise ValueError ('Unexpected split_name length: %d' % len(split_name))

    hosts = int(hosts[:hosts.find('h')])

    if state != 'state':
        raise ValueError('tree state files must start with the word state')
    if nodfr != 'nodfr':
        raise ValueError('adst tree state files must include \'nodfr\'')

    return topo, bisec, radix, hosts, model, num_trees

def get_sim_info_edst(fname):
    if fname.rfind('/') >= 0:
        simname = fname[fname.rfind('/')+1:]
    else:
        simname = fname
    split_name = simname.split('.')

    # state.jellyfish.B2.64r.2048h.edst.mlayer-4.8-t.9.json
    if len(split_name) == 9:
        state, topo, bisec, radix, hosts, model, ttg, run, json = split_name
        num_trees = 'max'
    elif len(split_name) == 10:
        state, topo, bisec, radix, hosts, model, ttg, num_trees, run, json = split_name
        if num_trees == '-1-t':
            num_trees = 'max'
    else:
        print simname
        print split_name
        raise ValueError ('Unexpected split_name length: %d' % len(split_name))

    hosts = int(hosts[:hosts.find('h')])

    if state != 'state':
        raise ValueError('tree state files must start with the word state')

    return topo, bisec, radix, hosts, model, ttg, num_trees

def parse_files(fnames, args):
    data = {}
    state = {}

    #t_topo, t_bisec, t_radix, t_hosts, t_model, t_ttg, t_num_trees = get_sim_info(fnames[0])
    t_topo = get_sim_info(fnames[0])[0]
    for fname in fnames:
        if fname.find('edst') >= 0:
            topo, bisec, radix, hosts, model, ttg, num_trees = get_sim_info_edst(fname)
        elif fname.find('adst') >= 0:
            topo, bisec, radix, hosts, model, num_trees = get_sim_info_adst(fname)
            ttg = 'nodfr'
        else:
            raise ValueError

        # Sanity checking the files that we are parsing
        if topo != t_topo:
            sys.stderr.write('ERROR: Mixing results of differing topologies\n')
            return

        if radix not in data:
            data[radix] = {}
        if bisec not in data[radix]:
            data[radix][bisec] = {}
        if model not in data[radix][bisec]:
            data[radix][bisec][model] = {}
        if hosts not in data[radix][bisec][model]:
            data[radix][bisec][model][hosts] = {}
        if ttg not in data[radix][bisec][model][hosts]:
            data[radix][bisec][model][hosts][ttg] = {}
        if num_trees not in data[radix][bisec][model][hosts][ttg]:
            data[radix][bisec][model][hosts][ttg][num_trees] = {}

        with open(fname) as f:
            try:
                results = yaml.load(f)

                maxes = {'host_tcam_bits': 0, 'sw_tcam_bits': 0, 'nopkthdr_sw_tcam_bits': 0}
                for sw in results:
                    # Validating the label bits
                    if ttg == 'nodfr':
                        if results[sw]['label_bits'] <= 0:
                            raise ValueError ('EDST without DFR must use some label bits')
                    elif model =='edst':
                        # DFR does not need any state
                        if results[sw]['label_bits'] > 0:
                            print 'Setting label bits to 0 even though they ' \
                                'are not because DFR does not require any ' \
                                'extra label bits'
                            results[sw]['label_bits'] = 0

                    tcam_width = (results[sw]['label_bits'] + results[sw]['port_bits'])
                    host_tcam_bits = results[sw]['hosts_tcam'] * tcam_width
                    sw_tcam_bits = results[sw]['sw_tcam'] * tcam_width
                    nopkthdr_sw_tcam_bits = results[sw]['nopkthdr_sw_tcam'] * tcam_width
                    maxes['host_tcam_bits'] = max(maxes['host_tcam_bits'], host_tcam_bits)
                    maxes['sw_tcam_bits'] = max(maxes['sw_tcam_bits'], sw_tcam_bits)
                    maxes['nopkthdr_sw_tcam_bits'] = max(maxes['nopkthdr_sw_tcam_bits'], nopkthdr_sw_tcam_bits)
                    data[radix][bisec][model][hosts][ttg][num_trees] = maxes
            except KeyboardInterrupt:
                raise
            except:
                traceback.print_exc(file=sys.stderr)
                tables = {}
                print '%s cannot be parsed' % fname
                #raise

    if args.prefix:
        prefix = args.prefix + '.'
    else:
        prefix = ''

    # Open up a file with the right ts
    outfname = 'tree_state.%s%s.%s.yaml' % (prefix, topo, model)

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

    # Optionally write the state to the chosen filename
    parser.add_argument('-p', '--prefix',
        help='A prefix to add to the resulting output files.')

    # The files to parse
    parser.add_argument('files', nargs='+', \
        help='The output files')

    args = parser.parse_args()

    parse_files(args.files, args)

if __name__ == "__main__":
    main()
