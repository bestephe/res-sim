#!/usr/bin/python

import argparse
import sys
import traceback
import yaml
from collections import deque

def gen_yaml(stream, emit_i):
    parent = None
    curr_i = 0
    events = {}
    tmp_events = []
    nodes_req, nodes_left = 0, 0
    doc_ses = [yaml.StreamStartEvent(), yaml.DocumentStartEvent()]
    doc_ees = [yaml.DocumentEndEvent(), yaml.StreamEndEvent()]

    def get_events(level = 0):
        if level not in events:
            return tmp_events
        else:
            es, end_es = events[level]
            ret = es + get_events(level + 1) + list(end_es)
            if level == 0:
                ret = doc_ses + ret + doc_ees
            return ret

    for event in yaml.parse(stream, Loader=yaml.CLoader):
        if isinstance(event, (yaml.DocumentStartEvent, yaml.StreamStartEvent,
                              yaml.DocumentEndEvent, yaml.StreamEndEvent)):
            continue

        if curr_i not in events:
            events[curr_i] = [], deque()
        es, end_es = events[curr_i]

        # Update the indentation
        if isinstance(event, yaml.SequenceStartEvent):
            if curr_i < emit_i:
                es.append(event)
                end_es.appendleft(yaml.SequenceEndEvent())
            else:
                tmp_events.append(event)
            curr_i += 1
            if curr_i == emit_i:
                nodes_req, nodes_left = 1, 1
        elif isinstance(event, yaml.MappingStartEvent):
            if curr_i < emit_i:
                es.append(event)
                end_es.appendleft(yaml.MappingEndEvent())
            else:
                tmp_events.append(event)
            curr_i += 1
            if curr_i == emit_i:
                nodes_req, nodes_left = 2, 2
        elif isinstance(event, yaml.SequenceEndEvent):
            if curr_i >= emit_i:
                tmp_events.append(event)
            curr_i -= 1
            if curr_i == emit_i:
                nodes_left -= 1
            if curr_i < emit_i:
                del events[curr_i]
                tmp_events = []
        elif isinstance(event, yaml.MappingEndEvent):
            if curr_i >= emit_i:
                tmp_events.append(event)
            curr_i -= 1
            if curr_i == emit_i:
                nodes_left -= 1
            if curr_i < emit_i:
                del events[curr_i]
                tmp_events = []
        else:
            if curr_i < emit_i:
                es.append(event)
            else:
                tmp_events.append(event)
            if curr_i == emit_i:
                nodes_left -= 1

        if emit_i == curr_i and nodes_left <= 0:
            doc = yaml.load(yaml.emit(get_events(), Dumper=yaml.CDumper),
                            Loader=yaml.CLoader)
            yield doc
            tmp_events = []
            nodes_left = nodes_req


def parse_files(fnames):
    data = {}
    for fname in fnames:
        if fname.rfind('/') >= 0:
            simname = fname[fname.rfind('/')+1:]
        else:
            simname = fname
        split_name = simname.split('.')
        radix, hosts, fail = split_name[2], split_name[3], split_name[4]
        hosts = int(hosts[:hosts.find('h')])

        switches, sw_tables = set(), {}

        if radix not in data:
            data[radix] = {}
        if fail not in data[radix]:
            data[radix][fail] = {}
        tables = {}
        with open(fname) as f:
            try:
                for doc in gen_yaml(f, 1):
                    assert(len(doc.keys()) == 1)
                    rootsw = doc.keys()[0]
                    for currsw in doc[rootsw].keys():
                        if rootsw not in switches:
                            switches.add(rootsw)
                            sw_tables[rootsw] = set()
                        if currsw not in tables:
                            tables[currsw] = 0
                        sw_tables[rootsw].add(currsw)
                        min_tcam = min(doc[rootsw][currsw].values())
                        #XXX: Hack - Remove the Drop Rule
                        tables[currsw] += (min_tcam - 1)
            except KeyboardInterrupt:
                raise
            except:
                traceback.print_exc(file=sys.stderr)
                #print '%s cannot be parsed' % fname


        for sw in switches:
            if sw_tables[sw] != switches:
                print '%s is incomplete!' % fname
                break
        #for sw, tcamsize in tables.iteritems():
        #    print '%s: %d' % (sw, tcamsize)
        if len(tables) > 0:
            maxtable = max(tables.values())
            data[radix][fail][hosts] = maxtable
        else:
            print '%s is empty!' % fname
    for radix in data:
        for fail in data[radix]:
            numhosts = data[radix][fail].keys()
            numhosts.sort()
            tcam_sizes = [data[radix][fail][num] for num in numhosts]
            data[radix][fail] = {'numhosts':numhosts, 'tcam_sizes':tcam_sizes}
    yaml.dump(data, sys.stdout)

def main():
    # Create the parser and subparsers
    parser = argparse.ArgumentParser(
        description='Parse the output files for TCAM state.')

    # Optionally check for correctness
    parser.add_argument('-c', '--check', help='Check the files for completeness')

    # The files to parse
    parser.add_argument('files', nargs='+', \
        help='The output files')
        

    args = parser.parse_args()
    parse_files(args.files)

if __name__ == "__main__":
    main()
