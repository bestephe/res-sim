#!/usr/bin/python

#Copyright (c) 2016, Brent Stephens
#All rights reserved.
#
#Redistribution and use in source and binary forms, with or without
#modification, are permitted provided that the following conditions are met:
#
#* Redistributions of source code must retain the above copyright notice, this
#  list of conditions and the following disclaimer.
#
#* Redistributions in binary form must reproduce the above copyright notice,
#  this list of conditions and the following disclaimer in the documentation
#  and/or other materials provided with the distribution.
#
#THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
#AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
#IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
#FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
#DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
#SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
#CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
#OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os, sys
#nx_lib_path = os.path.abspath('.')
#sys.path.insert(0, nx_lib_path)

import argparse
import itertools
import json
import ijson
import itertools
import math
import numpy
#import networkx as nx
import random
import scipy
import yaml
from collections import deque
from yaml import CLoader as Loader, CDumper as Dumper
from tree_alg import *
from priority_dict import *

# Trick for accomplishing Enums in old python
def enum(**enums):
    return type('Enum', (), enums)

# String enums for argument parsing and checking
Models = enum(EDST = 'edst', ADST = 'adst')

class Host:
    def __init__(self, name, v, portno):
        self.name = name
        self.v = v
        self.portno = portno

    def __repr__(self):
        return self.name

class Flow:
    def __init__(self, src, dst):
        self.src = src
        self.dst = dst
        self.path = None
        self.ports = set()
        self.rate = 0.0
        self.fail_exp = False

    def reset(self):
        self.path = None
        self.ports = set()
        self.rate = 0
        #self.fail_exp = False

    def __repr__(self):
        return '%s -> %s' % (self.src, self.dst)

class Port:
    def __init__(self, name, portno):
        self.name = name
        self.portno = portno
        self.rate = 1.0 # Optionally set to a large number and use ints
        self.used = 0.0
        # Only contains unassigned flows. Becomes empty eventually.
        self.flows = set()
        #self.unassigned_flows = 0

    def flow_rate(self):
        if len(self.flows) > 0:
            return (self.rate - self.used) / len(self.flows)
        else:
            return 0

    def reset(self):
        self.used = 0.0
        self.flows = set()
        self.unassigned_flows = 0

    def __repr__(self):
        return '%s-%s' % (self.name, self.portno)

class Fwdtable(dict):
    def __repr__(self):
        return 'table-%d' % self.i

def build_fwdtable(V, E, tf, args):
    # Build tables of vertex and edge names for forwarding table parsing
    num_v = {}
    for v in V:
        num_v[v.vnum] = v
    num_e = {}
    for e in E:
        num_e[e.enum] = e

    # Build the forwarding tables
    fwdtable = Fwdtable()

    #TODO: If this actually takes too much time, we need a parser from
    # ijson.parse
    #print 'Parsing tf...'
    for subtable in ijson.items(tf, "item"):
        for vnum in subtable:
            v = num_v[int(vnum)]
            if v not in fwdtable:
                fwdtable[v] = {}
            for entry in subtable[vnum]:
                key, value = entry
                dsti, ctreei, utreei, ei = key
                port, mark_failed = value
                dst = num_v[int(dsti)]
                e = num_e[int(ei)]
                #XXX: TODO: fail less extremely
                assert(e.v1 == v and e.p1 == port or e.v2 == v and e.p2 == port)
                assert(port in v.ports)
                if (dst, ctreei) not in fwdtable[v]:
                    fwdtable[v][dst, ctreei] = []
                fwdtable[v][dst, ctreei].append(((utreei, e), (port, mark_failed)))
    return fwdtable

def build_hosts(V, args):
    hosts = []
    for v in V:
        for h_i, (portno, h) in enumerate(v.host_ports.iteritems()):
            host = Host(h, v, portno)
            hosts.append(host)
    return hosts

def build_ports(hosts, V):
    ports = []
    for h in hosts:
        ports.append(Port(h, 0))
    for v in V:
        for portno in v.ports:
            ports.append(Port(v, portno))
        for portno in v.host_ports:
            ports.append(Port(v, portno))
    return ports

def urand(hosts, r):
    flows = []
    for h in hosts:
        for i in range(r):
            dst = random.choice(hosts)
            while dst is h:
                dst = random.choice(hosts)
            flows.append(Flow(h, dst))
    return flows

def uniform(hosts):
    flows = []
    for h in hosts:
        for dst in hosts:
            if dst != h:
                flows.append(Flow(h, dst))
    return flows

def local_failed(v, failedE):
    localFailedE = set()
    #TODO
    return localFailedE

def correlated_edge_fail(E, num_failures):
    if num_failures == 0:
        return frozenset()
    elif num_failures >= len(E):
        return frozenset(E)

    failedE = set(random.sample(E, 1))
    failedEl = list(failedE)
    while len(failedE) < num_failures:
        next_e = None
        while next_e == None:
            curr_e = random.choice(failedEl)
            adj_es = [e for e in curr_e.v1.edges.itervalues() if e not in failedE]
            adj_es.extend([e for e in curr_e.v2.edges.itervalues() if e not in failedE])
            if len(adj_es) > 0:
                next_e = random.choice(adj_es)
        failedE.add(next_e)
        failedEl.append(next_e)
    return failedE

def correlated_vertex_fail(V, num_failures):
    if num_failures == 0:
        return frozenset()
    elif num_failures >= len(V):
        return frozenset(V)

    failedV = set(random.sample(V, 1))
    failedVl = list(failedV)
    while len(failedV) < num_failures:
        next_v = None
        while next_v == None:
            curr_v = random.choice(failedVl)
            adj_vs = [v for v in curr_v.ports.itervalues() if v not in failedV]
            if len(adj_vs) > 0:
                next_v = random.choice(adj_vs)
        failedV.add(next_v)
        failedVl.append(next_v)
    return failedV

def init_topk_cache(V):
    for v in V:
        v.topk = {d: [] for d in V}

#XXX: this should really be part of tree_alg.py, but it currently can't because
# tree_alg.py only builds one forwarding table, not the 8-way ECMP that is
# available
#XXX: This function has two magic numbers (1.35x and top-8) that should be
# defined elsewhere
def populate_topk_cache(src_v, dst_v, fwdtables, iG_shortest_paths):
    assert(len(src_v.topk[dst_v]) == 0)

    assert (src_v != dst_v)

    forest = []
    for fwdtable in fwdtables:
        start_trees = [(fwdtable, entry[0][0]) for entry in fwdtable[src_v][dst_v, 0]]
        # Error checking: there should always be at least one valid tree.
        # Note: this requires a topology that is initially connected
        assert(len(start_trees) > 0)
        forest.extend(start_trees)
    random.shuffle(forest)

    #forest_paths = [fwdtable_walk_path_internal(src_v, dst_v, fwdtable, \
    #    itree, frozenset(), frozenset())[0] for fwdtable, itree in forest]
    #forest_paths_lens = [len(hops) for hops in forest_paths]

    # Find the length of the paths for all of the startin gtrees
    forest_paths_lens = [len(fwdtable_walk_path_internal(src_v, dst_v, fwdtable, \
        itree, frozenset(), frozenset())[0]) for fwdtable, itree in forest]

    # Sort the trees by the path length to the destination
    l = zip(forest, forest_paths_lens)
    l.sort(lambda x, y: cmp(x[1], y[1]))

    # Find the shortest path pathlength for comparison
    shortest_pathlen = iG_shortest_paths[src_v.igid][dst_v.igid]

    #DEBUG
    #print forest_paths_lens
    #print l
    #print 'shortest_pathlen:', shortest_pathlen

    # Check if the best path is *good* enough (< 1.35x longer).
    # If so, keep all *good* paths. Otherwise, keep all of the *best* paths
    if 1.0 * l[0][1] / shortest_pathlen > 1.35:
        # Just keep all of the trees that are equal to our bad pathlength
        l = filter(lambda x: x[1] == l[0][1], l)

        #DEBUG
        #print 'WARNING: table path is %f times worse than the best path' % \
        #    (1.0 * l[0][1] / shortest_pathlen)
    else:
        l = filter(lambda x: 1.0 * x[1] / shortest_pathlen <= 1.35, l)

    # Truncate to at most top-8, remove the length, and cache the results
    src_v.topk[dst_v] = map(lambda x: x[0], l[:8])

    #DEBUG
    #print 'src_v.topk[dst_v]:', src_v.topk[dst_v]

def fwdtable_walk_path(src_v, dst, failedE, failedV):
    dst_v = dst.v

    if src_v != dst_v:
        fwdtable, itree = random.choice(src_v.topk[dst_v])

        hops, fail_exp = fwdtable_walk_path_internal(src_v, dst_v, fwdtable, \
                            itree, failedE, failedV)
    else:
        hops, fail_exp = [], False

    # Add the last hop, which we never allow to fail
    if hops != None:
        hops.append(dst.portno)
    else:
        assert(fail_exp)

    return hops, fail_exp

def fwdtable_walk_path_internal(src_v, dst_v, fwdtable, itree, failedE, failedV):

    #DEBUG
    #print 'fwdtable_walk_path'

    hops = []
    assert(itree != 0)
    ctree = itree
    failed_trees = set()
    v = src_v
    if v in failedV:
        return None, True
    fail_exp = False
    while v is not dst_v:
        assert(v not in failedV)

        # Get the local failed edges
        localFailedE = set()
        for port, edge in v.edges.iteritems():
            if edge in failedE:
                localFailedE.add(edge)
        localFailedE = frozenset(localFailedE)

        # DEBUG
        #print fwdtable[v]

        # Error checking: there should always be at least one valid tree.
        # Note: this requires a topology that is initially connected
        assert((dst_v, ctree) in fwdtable[v] if ctree == 0 else True)

        # Return early if there is no matching entry
        if (dst_v, ctree) not in fwdtable[v]:
            return None, True

        # Special case: ECMP to choose the first layer
        #XXX: This is a little unfair.  We should first just randomly choose
        #one of the current trees then pretend we are forwarding on it before
        #checking to see if our first random tree has failed.
        assert (ctree != 0)
        if ctree == 0:
            start_tree = random.choice(fwdtable[v][dst_v, ctree])[0][0]
            assert (type(start_tree) == type(1))
            ctree = start_tree

        entryl = fwdtable[v][dst_v, ctree]
        #print dst_v, ctree, '->', entryl

        # Now pick the first match
        ntree = None
        for entry in entryl:
            _ntree, _ue = entry[0]
            if _ntree not in failed_trees and _ue not in localFailedE:
                (ntree, ue), (port, mark_failed) = entry
                break

        # If no path was found, fail
        if ntree == None:
            return None, True

        assert (ntree not in failed_trees)
        assert (ue not in failedE)

        # Find the next vertex
        nv = v.ports[port]

        # DEBUG
        #print 'v:', v, 'nv:', nv, 'port:', port, 'ctree:', ctree, 'ntree:', ntree
        #print 'failed_trees:', failed_trees, 'mark_failed:', mark_failed
        #print

        # If we have changed trees, then we have experienced a failure
        if ntree != ctree:
            fail_exp = True

        # Update the hops, current tree, the faield trees, and v
        hops.append(port)
        ctree = ntree
        failed_trees.update(set(mark_failed))
        v = nv

    return hops, fail_exp

def build_fwdtable_paths(flows, fwdtables, failedE, failedV, iG_shortest_paths):
    for flow in flows:
        src_v = flow.src.v
        dst = flow.dst
        dst_v = dst.v
        
        # Find the top-k starting trees for this source and destination pair if
        # it does not yet exist
        if len(src_v.topk[dst_v]) == 0 and src_v != dst_v:
            populate_topk_cache(src_v, dst_v, fwdtables, iG_shortest_paths)

        path, fail_exp = fwdtable_walk_path(src_v, dst, failedE, failedV)
        flow.path = path
        flow.fail_exp = fail_exp

        #DEBUG
        #if fail_exp:
        #    print '%s -> %s experienced a failure' % (flow, path)

        #XXX DEBUG
        #print 'failedE:', failedE
        #print 'flow:', flow, 'flow.path:', path
        
        #XXX: DEBUG to assert full resilience
        #assert(flow.path != None)
        #if path is not None and len(path) > 1:
        #    p = Path(src_v, path[:-1])
        #    v, rp = revpath_at_fail(p, set())
        #    assert(v == dst.v)

def build_shortest_paths(flows, V, E, iG, failedE = set(), failedV = set(), fail = 'edges'):
    # Optimization so that the nonfailed subgraph only needs to be computed once
    #XXX: Implement sub_iG optimization
    if not iG.is_directed():
        sub_iG = None
        if fail == 'edges':
            upE = E - failedE
            eigids = [e.igid for e in upE]
            #eigids = [iG.es.find(name=e).index for e in upE]
            sub_iG = iG.subgraph_edges(eigids)
        elif fail == 'vertices':
            upV = V - failedV
            vigids = [v.igid for v in upV]
            #vigids = [iG.vs.find(name=v.name).index for v in upV]
            sub_iG = iG.subgraph(vigids)
    else:
        sub_iG = iG

    for flow in flows:
        if fail == 'vertices' and flow.dst.v in failedV:
            flow.path = None
        else:
            path = shortest_path(V, E, sub_iG, flow.src.v, flow.dst.v, fail = 'none')
                #XXX: failedE = failedE, failedV = failedV, fail = fail)
            if path.path is None:
                if flow.src.v == flow.dst.v and flow.src.v not in failedV:
                    flow.path = [flow.dst.portno]
                else:
                    flow.path = None
            else:
                fp = list(path.path)
                assert(len(fp) > 0)
                fp.append(flow.dst.portno)
                flow.path = fp

def reset_flows(flows):
    for flow in flows:
        flow.reset()

def reset_ports(ports):
    for port in ports:
        port.reset()

def init_ports(port_dict, flows):
    for flow in flows:
        # Quit if there is no path
        if flow.path is None:
            continue

        # Add the flows to the ports
        v = flow.src.v
        port = port_dict[(flow.src, 0)]
        port.flows.add(flow)
        flow.ports.add(port)
        for hop_i, hop in enumerate(flow.path):
            port = port_dict[(v, hop)]
            port.flows.add(flow)
            flow.ports.add(port)
            if hop_i != len(flow.path) - 1:
                try:
                    v = v.ports[hop]
                except KeyError:
                    print 'flow:', flow, 'flow.path:', flow.path
                    print 'v:', v, 'v.ports:', v.ports
                    raise
                    

def compute_flow_throughputs(ports):
    # Function for walking path to assign a flow

    # Build the port priority queue
    portpq = priority_dict()
    for port in ports:
        portpq[port] = port.flow_rate()

    # Iterate the priority queue
    while len(portpq) > 0:
        updated_ports = set()
        port = portpq.pop_smallest()

        # Get the rate and quit continue if it is 0.0
        rate = port.flow_rate()
        if rate is 0:
            continue
        
        # Assign the flow rate to all of the flows on this port.
        # Also update the affected ports by this assignment
        for flow in port.flows.copy():
            flow.rate = rate
            for fp in flow.ports:
                fp.used += rate
                assert(fp.used <= 1.01)
                fp.flows.remove(flow)
                updated_ports.add(fp)
        assert(len(port.flows) is 0)
        #print port.used
        assert(port.used >= 0.99 and port.used <= 1.01)

        for up in updated_ports:
            portpq[up] = up.flow_rate()

def main():
    # Create the parser
    parser = argparse.ArgumentParser(
        description='Given tree forwarding tables, compute throughput and '
        'stretch and compare against shortest path routing')

    # The number of elements to fail
    parser.add_argument('-n', '--num-failures', type=int, required=True,
        help='The number of either edges or vertices to fail.')

    # The degree of communication
    parser.add_argument('-d', '--degree', type=int, required=True,
        help='Degree of random communication.')

    # Whether failures are correlated or not
    parser.add_argument('-c', '--correlated-fail', action='store_true',
        help='Optionally use correlated failures instead of random failures.')

    # Use ECMP routing or not
    parser.add_argument('-e', '--ecmp', action='store_true',
        help='Randomize the paths used.  If not set, then they are used for '
        'the hosts in order.')

    # Forwarding model
    #TODO: this is actual model independent? I think?
    #parser.add_argument('--model', required=True,
    #    choices=(Models.EDST, Models.ADST),
    #    help='Same meaning as tree_alg.py.  The forwarding model to use. ' +
    #     Models.EDST + ' is for ' 'edge-disjoint trees and ' + Models.ADST +
    #     'is for arc-disjoint trees.')

    # Fail either edges or vertices
    parser.add_argument('--fail', default='edges',
        choices=('edges', 'vertices', 'vert-and-last-edge'), #TODO: implement this
        help='Fail either edges or vertices')

    # The input topology
    parser.add_argument('topo', type=argparse.FileType('r'),
        help='The YAML for the generated topology. MUST be syntactically '
        'correct (e.g. the output from the topology generator (topo_gen.py)')

    # The files to parse
    parser.add_argument('tables', nargs='+', \
        help='The forwarding table YAML files.')

    # Parse the arguments
    args = parser.parse_args()

    # Parse the topology
    topo = yaml.load(args.topo, Loader=yaml.CLoader)
    switches = topo['Switches']
    G = build_graph(switches)
    V, E = G
    iG = mygraph_to_igraph(V, E)
    iG_shortest_paths = iG.shortest_paths()

    #DEBUG
    #print 'iG_shortest_paths:', iG_shortest_paths

    #print '|V|:', len(V)
    #print '|E|:', len(E)

    # Parse and build the forwarding tables
    fwdtables = []
    for table_i, tfname in enumerate(args.tables):
        with open(tfname) as tf:
            #table = yaml.load(tf, Loader=yaml.CLoader)
            #table = json.load(tf)
            #print 'Building a fwdtable...'
            try:
                fwdtable = build_fwdtable(V, E, tf, args)
            except:
                print 'Error parsing file: %s' % tfname
                sys.stderr.write('Error parsing file: %s\n' % tfname)
                raise
            fwdtable.i = table_i
            fwdtables.append(fwdtable)
    random.shuffle(fwdtables)

    failed_table_flows = 0
    failed_short_flows = 0
    tot_flows = 0
    table_avg_tput = IncAvg()
    short_avg_tput = IncAvg()
    stretches = []
    fail_stretches = []
    fail_runs_table = []
    fail_runs_short = []

    init_topk_cache(V)

    # Repeatedly check failed edges for throughput
    #for failedE in itertools.combinations(E, args.num_failures):
    for i in xrange(100):

        # Randomize the forwarding table order
        random.shuffle(fwdtables)

        # Build the hosts
        hosts = build_hosts(V, args)
        #print hosts

        # Build the ports
        ports = build_ports(hosts, V)
        port_dict = {(p.name, p.portno): p for p in ports}
        #print ports
        #print port_dict

        # Build the workload
        flows = urand(hosts, args.degree)
        #flows = uniform(hosts)

        tot_flows += len(flows)

        # Select the failed sets
        if args.fail == 'edges':
            if args.num_failures is -1 or args.num_failures > len(E):
                args.num_failures = len(E)
            if args.correlated_fail:
                failedE = correlated_edge_fail(E, args.num_failures)
                #print 'correlated failedE:', failedE
            else:
                failedE = frozenset(random.sample(E, args.num_failures))
            failedV = frozenset()
        elif args.fail == 'vertices':
            if args.num_failures is -1 or args.num_failures > len(V):
                args.num_failures = len(V)
            if args.correlated_fail:
                failedV = correlated_vertex_fail(V, args.num_failures)
                #print 'correlated failedV:', failedV
            else:
                failedV = frozenset(random.sample(V, args.num_failures))
            failedE = set()
            for fv in failedV:
                failedE.update(fv.edgeSet)
            failedE = frozenset(failedE)
        #failedE = frozenset(failedE)
        #failedV = frozenset(failedV)

        for path_model in ('fwdtable', 'shortest'):
            #print 'Path Model:', path_model

            # Reset then calculate the paths of the flows
            reset_flows(flows)
            if path_model == 'fwdtable':
                build_fwdtable_paths(flows, fwdtables, failedE, failedV, iG_shortest_paths)
                failed_table_flows_run = 0
                for flow in flows:
                    if flow.path == None:
                        failed_table_flows += 1
                        failed_table_flows_run += 1
                        flow.table_pathlen = 0
                    else:
                        flow.table_pathlen = len(flow.path) + 1 # The hop from src to v
                fail_runs_table.append([failed_table_flows_run, len(flows)])
            else:
                build_shortest_paths(flows, V, E, iG, failedE, failedV, args.fail)
                failed_short_flows_run = 0
                for flow in flows:
                    if flow.path == None:
                        failed_short_flows += 1
                        failed_short_flows_run += 1
                        flow.short_pathlen = 0
                    else:
                        flow.short_pathlen = len(flow.path) + 1 # The hop from src to v
                fail_runs_short.append([failed_short_flows_run, len(flows)])
            
            #XXX: DEBUG
            #for flow in flows:
            #    print flow, flow.path

            # Reset and Init the ports
            reset_ports(ports)
            init_ports(port_dict, flows)

            #XXX: DEBUG
            #for port in ports:
            #    print port, port.flows
            
            # Compute Flow Throughput
            compute_flow_throughputs(ports)
            agg_tput = reduce(lambda agg, f: agg + f.rate, flows, 0)
            if path_model == 'fwdtable':
                table_avg_tput.update(agg_tput)
            else:
                short_avg_tput.update(agg_tput)

            #XXX: DEBUG
            for flow in flows:
                #print flow, flow.path, flow.rate
                if flow.path is not None:
                    tmp_path = Path(flow.src.v, flow.path[:-1])
                    #print 'vertices:', tmp_path.vertices
                    assert(len(failedV.intersection(tmp_path.vertices)) == 0)
                    assert(len(failedE.intersection(tmp_path.edges)) == 0)
                #print flow, flow.path, tmp_path.vertices

            #TODO: Remember to deal with flows that enter part-way into the
            # network but fail to reach their destination. They consume
            # bandwidth, but don't attribute to aggregate throughput.
            #TODO: But TCP flows won't continue to waste bandwidth. For now
            # I'll just assume they don't consume bandwidth
        
        # Compute stretch
        for flow in flows:
            if flow.table_pathlen > 0 and flow.short_pathlen > 0:
                stretch = 1.0 * flow.table_pathlen / flow.short_pathlen
                stretches.append(stretch)
                if flow.fail_exp:
                    fail_stretches.append(stretch)

    # Compute median and 99p stretch
    #XXX: It would be better to upgrade to scipy version 0.13.0 where multiple
    # percentiles are passable to scipy.stats.scoreatpercentile(stretches, [50, 99])
    stretches.sort()
    if len(stretches) == 0:
        stretches.append(1.0)
    median = numpy.asscalar(scipy.stats.scoreatpercentile(stretches, 50))
    ninetynine = numpy.asscalar(scipy.stats.scoreatpercentile(stretches, 99))
    threenine = numpy.asscalar(scipy.stats.scoreatpercentile(stretches, 99.9))
    fournine = numpy.asscalar(scipy.stats.scoreatpercentile(stretches, 99.99))
    fivenine = numpy.asscalar(scipy.stats.scoreatpercentile(stretches, 99.999))
    maxstretch = max(stretches)

    fail_stretches.sort()
    if len(fail_stretches) > 0:
        fmedian = numpy.asscalar(scipy.stats.scoreatpercentile(fail_stretches, 50))
        fninetynine = numpy.asscalar(scipy.stats.scoreatpercentile(fail_stretches, 99))
        fthreenine = numpy.asscalar(scipy.stats.scoreatpercentile(fail_stretches, 99.9))
        ffournine = numpy.asscalar(scipy.stats.scoreatpercentile(fail_stretches, 99.99))
        ffivenine = numpy.asscalar(scipy.stats.scoreatpercentile(fail_stretches, 99.999))
        fmaxstretch = max(fail_stretches)
    else:
        fmedian = None
        fninetynine = None
        fthreenine = None
        ffournine = None
        ffivenine = None
        fmaxstretch = None

    output = {
        'fail_runs_table': fail_runs_table,
        'fail_runs_short': fail_runs_short,
        'failed_table_flows': failed_table_flows,
        'failed_short_flows': failed_short_flows,
        'tot_flows': tot_flows,
        'table_avg_tput': table_avg_tput.get(),
        'short_avg_tput': short_avg_tput.get(),
        'median_stretch': median,
        '99p_stretch': ninetynine,
        '99.9p_stretch': threenine,
        '99.99p_stretch': fournine,
        '99.999p_stretch': fivenine,
        'max_stretch': maxstretch,
        'median_fstretch': fmedian,
        '99p_fstretch': fninetynine,
        '99.9p_fstretch': fthreenine,
        '99.99p_fstretch': ffournine,
        '99.999p_fstretch': ffivenine,
        'max_fstretch': fmaxstretch,
        'num_stretch': len(stretches),
        'num_fstretch': len(fail_stretches),
    }

    yaml.dump(output, sys.stdout)

if __name__ == "__main__":
    main()
