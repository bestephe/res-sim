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
import networkx as nx
import random
import scipy
import yaml
from collections import deque
from yaml import CLoader as Loader, CDumper as Dumper
from resnet_alg import *
from priority_dict import *

class Arc:
    def __init__(self, v, e):
        self.v = v
        self.e = e

    def __repr__(self):
        return repr((self.v, self.e))
    
    #XXX: needed to print graphs
    def __len__(self):
        return len(repr(self))

def build_fwdtable(V, E, tf, args):
    # Build tables of vertex and edge names for forwarding table parsing
    num_v = {}
    for v in V:
        num_v[v.vnum] = v
    num_e = {}
    for e in E:
        num_e[e.enum] = e

    # Build the forwarding tables
    fwdtable = {}

    #TODO: If this actually takes too much time, we need a parser from
    # ijson.parse
    #print 'Parsing tf...'
    for subtable in ijson.items(tf, "item"):
        for vnum in subtable:
            v = num_v[int(vnum)]
            if v not in fwdtable:
                fwdtable[v] = {}
            for entry in subtable[vnum]:
                key, out = entry
                assert(len(out) > 0)
                if args.model == 'plinko':
                    dstnum, rp, enum, fsnum = key
                    dst = num_v[int(dstnum)]
                    rp = tuple(rp)
                    e = num_e[int(enum)]
                    fs = set()
                    for fs_enum in fsnum:
                        fs_e = num_e[int(fs_enum)]
                        fs.add(fs_e)
                    fs = frozenset(fs)
                    if (dst, rp) not in fwdtable[v]:
                        fwdtable[v][dst, rp] = []
                    fwdtable[v][dst, rp].append(((e, fs), out))
                elif args.model == 'eth-fcp':
                    dstnum, kfsnum, enum, fsnum = key
                    dst = num_v[int(dstnum)]
                    kfs = set()
                    for kfs_enum in kfsnum:
                        kfs_e = num_e[int(kfs_enum)]
                        kfs.add(kfs_e)
                    e = num_e[int(enum)]
                    fs = set()
                    for fs_enum in fsnum:
                        fs_e = num_e[int(fs_enum)]
                        fs.add(fs_e)
                    kfs = frozenset(kfs)
                    fs = frozenset(fs)
                    if (dst, kfs) not in fwdtable[v]:
                        fwdtable[v][dst, kfs] = []
                    fwdtable[v][dst, kfs].append(((e, fs), out))
    return fwdtable

def build_arcs(V):
    arcs = []
    for v in V:
        v.arcs = {port: Arc(v, v.edges[port]) for port in v.edges}
        arcs.extend(v.arcs.itervalues())
    return set(arcs)

def plinko_path_cdg(path, src, dst, fwdtable):
    stack = [(path, (), src, dst, None)]
    arcs = set()
    dependencies = set()

    while len(stack) > 0:
        # Get the current path, reversepath, vertex, dst, and arc for
        # dependency
        cp, crp, cv, cdst, parc = stack.pop()

        # DEBUG
        #print 'stack pop:', 'p:', cp, 'crp:', crp, 'cv:', cv, 'parc:', parc

        # Walk the path, finding arcs and dependencies and new paths
        rev_path = []
        for hop_i, hop in enumerate(cp):
            # Add this arc
            carc = cv.arcs[hop]
            arcs.add(carc)

            # This arc and the previous are dependent on each other
            if parc != None:
                # No self loops, so assertion should be correct
                assert (parc.v != carc.v)
                dependencies.add((parc, carc))

            # Search for new paths to add to the stack.  The 0th table was
            # already used to find this entry, so skip it.
            nrp = crp + tuple(rev_path)
            if hop_i > 0 and (dst, nrp) in fwdtable[cv]:
                assert(parc != None)
                for (e, fs), out in fwdtable[cv][dst, nrp]:
                    stack.append((out, nrp, cv, dst, parc))

            # Update loop variables
            nv, rhop = cv.edges[hop].get_other(cv, hop)
            cv = nv
            parc = carc
            rev_path.append(rhop)

    #DEBUG
    #print 'arcs:', arcs
    #print 'dependencies:'
    #for dep in dependencies:
    #    print '   ', dep

    # Start creating our Channel Dependency Graph
    cdg = igraph.Graph(directed=True)
    vs = list(arcs)
    cdg.add_vertices(vs)

    # Map arcs to igraph indices
    arc2ig = {iv['name']: iv.index for iv in cdg.vs}

    # Get the edges to add
    edges = [(arc2ig[parc], arc2ig[carc]) for parc, carc in dependencies]
    cdg.add_edges(edges)

    # DEBUG
    #print cdg

    # If a path branchings CDG contains self cycles (uses the same arc twice),
    # then there is no possible deadlock freedom.
    assert(cdg.is_dag())
    assert(cdg.is_connected(igraph.WEAK))

    return cdg

def get_path_cdgs(fwdtables):
    cdgs = []
    for fwdtable in fwdtables:
        for v in fwdtable:
            for dst, rp in fwdtable[v]:
                for (e, fs), out in fwdtable[v][dst, rp]:
                    if rp == ():
                        # CDG: Channel Dependency Graph
                        cdg = plinko_path_cdg(out, v, dst, fwdtable)
                        cdg.es['cdg_num'] = [len(cdgs)] * len(cdg.es)
                        cdgs.append(cdg)

    return cdgs

# Combine multiple CDGs into a CDG for a single virtual channel
def build_cdg_vc_networkx(A, cdgs):
    #vc = nx.MultiDiGraph()
    vc = nx.DiGraph()
    for a in A:
        vc.add_node(a)
    #vc.add_nodes_from(A)

    for cdg in cdgs:
        for ie in cdg.es:
            src = cdg.vs[ie.source]['name']
            tgt = cdg.vs[ie.target]['name']
            vc.add_edge(src, tgt, attr_dict = {'cdg_num': ie['cdg_num']})

    #print 'number of nodes:', vc.number_of_nodes()
    #print 'number of edges:', vc.number_of_edges()
    #cycles = nx.simple_cycles(vc)
    #for cycle in cycles:
    #    print 'cycle:', cycle

    return vc

# Networkx has cycle detection implemented.  Igraph does not.  Ugly as hell,
# but I'm using igraph now.

# Combine multiple CDGs into a CDG for a single virtual channel
def build_cdg_vc(A, cdgs):
    #TODO: perhaps igraph.Graph.union is the correct thing to do here
    #XXX: Does not seem like this works!
    #return reduce(lambda x, y: x.union(y), cdgs)

    # Build the virtual channel
    vc = igraph.Graph(directed=True)
    vc.add_vertices(A)

    # Map arcs to igraph indices
    arc2ig = {iv['name']: iv.index for iv in vc.vs}

    #DEBUG
    #present_arcs = {}

    for cdg in cdgs:
        new_edges = []
        cdg_num = -1
        for ie in cdg.es:
            src = arc2ig[cdg.vs[ie.source]['name']]
            tgt = arc2ig[cdg.vs[ie.target]['name']]
            new_edges.append((src, tgt))

            #TODO: if (src, tgt) already exists for this CDG, then when should
            # not add the edge again
            #vc.add_edge(src, tgt, cdg_num = ie['cdg_num'])

            if cdg_num == -1:
                cdg_num = ie['cdg_num']
            else:
                assert(cdg_num == ie['cdg_num'])

        maxidx = vc.ecount()
        vc.add_edges(new_edges)
        #print 'maxidx:', maxidx, 'vc.ecount():', vc.ecount()
        for i in range(maxidx, vc.ecount()):
            vc.es[i]['cdg_num'] = cdg_num

        #DEBUG
        #for ie in vc.es:
        #    print '   ', ie, ie['cdg_num']


            #DEBUG
            #if (src, tgt) not in present_arcs:
            #    present_arcs[src, tgt] = [ie['cdg_num']]
            #if (src, tgt) in present_arcs:
            #    present_arcs[src, tgt].append(ie['cdg_num'])
            #    print 'multiple edges 1:', src, '-->', tgt, '(', present_arcs[src, tgt], ')'
            #    #XXX: WARNING! vc.get_eids(...) is broken for multigraphs!
            #    # The workaround is to use vc.incident(src)
            #    #eids = vc.get_eids(pairs = [(src, tgt)])
            #    eids = filter(lambda x: vc.es[x].target == tgt, vc.incident(src))
            #    print '    eids:', eids
            #    for eid in eids:
            #        print '       ', vc.es[eid]
            #        print '        is_multiple:', vc.is_multiple(eid)


    #DEBUG:
    #print 'total edges:', sum(map(lambda x: len(x.es), cdgs))
    #print 'vc edges:', len(vc.es)
    #assert(sum(map(lambda x: len(x.es), cdgs)) == len(vc.es)) 

    # DEBUG
    #for iv in vc.vs:
    #    for iw in vc.vs:
    #        #XXX: WARNING! vc.get_eids(...) is broken for multigraphs!
    #        # The workaround is to use vc.incident(src)
    #        eids = filter(lambda x: vc.es[x].target == iw.index, vc.incident(iv.index))
    #        if len(eids) > 1:
    #            print 'multiple edges 2:', eids

    return vc

def break_cycle_cdg_vc(vc, cycle):
    #XXX: WARNING! vc.get_eids(...) is broken for multigraphs!
    # As the documentation says, it returns *some* of the edges, not all.
    # The workaround is to use vc.incident(src)
    #cycle_edges = [filter(lambda x: vc.es[x].target == cycle[i+1], vc.incident(cycle[i])) for i in range(len(cycle) - 1)]

    #XXX: Building cycle_edges this way to allow for quitting early
    cycle_edges = []
    for i in range(len(cycle) - 1):
        x = filter(lambda x: vc.es[x].target == cycle[i+1], vc.incident(cycle[i]))
        # Return early if links don't actually exist
        if len(x) == 0:
            #print 'quitting early'
            return []
        cycle_edges.append(x)

    # Find the number of paths in the weakest edge
    weakest_len = min(map(lambda x: len(x), cycle_edges))

    # If one of the edges does not exist, then we have already broken the cycle
    if  weakest_len == 0:
        #DEBUG
        #print 'Cycle was already broken!'

        return []

    # Find the edges were are removing to break the cycle
    remove_edges = random.choice(filter(lambda x: len(x) == weakest_len, cycle_edges))

    # Find the paths that induce the edges to remove
    remove_paths = set([vc.es[eid]['cdg_num'] for eid in remove_edges])

    # Find the eigids of all of the edges on the paths to remove
    eigids = [ie.index for ie in vc.es if ie['cdg_num'] in remove_paths]
    #eigids = filter(lambda ie: ie['cdg_num'] in remove_paths, vc.es)

    # Remove the eigids
    vc.delete_edges(eigids)

    # DEBUG
    #print 'cycle:', cycle
    #print 'cycle_edges:', cycle_edges
    #print 'removing edges:', remove_edges
    #print 'removing paths:', remove_paths
    #print 'eigids:', eigids
    #print

    return list(remove_paths)

# Returns a list of cdg_nums
def remove_cycles_cdg_vc(vc):
    removed = []

    #DEBUG
    #print 'Before vc.is_dag():', vc.is_dag()
    #print 'vc.is_connected(igraph.WEAK):', vc.is_connected(igraph.WEAK)

    # Find our starting ivs
    #XXX: This is wrong. We just start with all vertices
    #start_ivs = [iv for iv in vc.vs.select(lambda v: len(v.predecessors()) == 0)]
    #random.shuffle(start_ivs)
    #if len(start_ivs) == 0:
    #    start_ivs = [random.choice(vc.vs)]

    # Get the starting ivs
    start_ivs = [iv for iv in vc.vs]
    random.shuffle(start_ivs)

    # Initialize DFS loop variables
    visited = {iv.index: False for iv in vc.vs}
    # [] -> (currentv, previousv_l, previousv_set)
    stack = [(start_iv, [start_iv.index], set((start_iv.index,))) for \
        start_iv in start_ivs]

    # Perform a DFS
    while len(stack) > 0:
        iv, pv, spv = stack.pop()

        #DEBUG
        #print 'iv:', iv, 'pv:', pv, 'spv:', spv

        if visited[iv.index]:
            continue
        else:
            visited[iv.index] = True

        succ = iv.successors()
        random.shuffle(succ)
        for iw in succ:
            if iw.index in spv:
                idx = pv.index(iw.index)
                cycle = pv[idx:] + [iw.index]
                paths = break_cycle_cdg_vc(vc, cycle)
                removed.extend(paths)
            if visited[iw.index] == False:
                stack.append((iw, pv + [iw.index], spv | set((iw.index,))))

            #DEBUG
            #print '    visited', iw.index, ':', visited[iw.index]

    #XXX: this assertion can fail? Not sure why.
    #assert(all(visited.itervalues()))

    #TODO: Assert that vc is acyclic (vc.is_dag())
    #TODO: Something must be wrong with my implementation of this algorithm.
    # As described by Domke et al., one DFS pass should be enough to break all
    # cycles.

    #DEBUG
    #print 'After vc.is_dag():', vc.is_dag()

    #DEBUG
    #print 'removed paths:', removed
        
    return removed

def assign_vcs(A, cdgs):
    # Assumed in this function
    for cdg_i, cdg in enumerate(cdgs):
        if len(cdg.es) > 0:
            assert(cdg.es[0]['cdg_num'] == cdg_i)

    vcs = []
    next_vc_cdgs = cdgs
    while len(next_vc_cdgs) > 0:
        vc = build_cdg_vc(A, next_vc_cdgs)

        #XXX: I should be able to remove all cycles in one pass.  Current
        # algorithm does not though.  As long as it eventually succeeds and
        # performance is not limiting, I'm not sure I care
        removed_cdg_idxs = []
        while vc.is_dag() == False:
            more_remove = remove_cycles_cdg_vc(vc)
            #print 'more_remove:', more_remove
            removed_cdg_idxs.extend(more_remove)
        vcs.append(vc)

        #DEBUG
        #print 'removed_cdg_idxs:', removed_cdg_idxs
        print 'new vc.  Current #vcs:', len(vcs)

        next_vc_cdgs = map(lambda i: cdgs[i], removed_cdg_idxs)

    # All VCs CDGs must be DAGs
    assert(all(map(lambda vc: vc.is_dag(), vcs)))

    return vcs

# Combine multiple CDGs into a CDG for a single virtual channel
def build_cdg_vc_fas(A, cdgs):

    # Build the virtual channel
    vc = igraph.Graph(directed=True)
    vc.add_vertices(A)

    # Map arcs to igraph indices
    arc2ig = {iv['name']: iv.index for iv in vc.vs}

    #DEBUG
    #present_arcs = {}

    for cdg in cdgs:
        new_edges = []
        cdg_num = -1
        for ie in cdg.es:
            # Get the current cdg num
            if cdg_num == -1:
                cdg_num = ie['cdg_num']
            else:
                assert(cdg_num == ie['cdg_num'])

            src = arc2ig[cdg.vs[ie.source]['name']]
            tgt = arc2ig[cdg.vs[ie.target]['name']]

            eid = vc.get_eid(src, tgt, error = False)
            
            # If the edge is new, save it for adding later because adding edges
            # is a relatively expensive operation in igraph because it uses an
            # adjaceny matrix.
            if eid < 0:
                new_edges.append((src, tgt))
            # Otherwise update the cdg this eid is a member of
            else:
                vc.es[eid]['cdgs'].append(cdg_num)
                vc.es[eid]['num_cdgs'] += 1
                assert(len(vc.es[eid]['cdgs']) == vc.es[eid]['num_cdgs'])

        maxidx = vc.ecount()
        vc.add_edges(new_edges)
        #print 'maxidx:', maxidx, 'vc.ecount():', vc.ecount()
        for i in range(maxidx, vc.ecount()):
            assert('cdgs' not in vc.es[i].attributes() or \
                vc.es[i]['cdgs'] == None)
            assert('num_cdgs' not in vc.es[i].attributes() or \
                vc.es[i]['num_cdgs'] == None)
            vc.es[i]['cdgs'] = [cdg_num]
            vc.es[i]['num_cdgs'] = 1

    return vc

def assign_vcs_fas(A, cdgs):
    # Assumed in this function
    for cdg_i, cdg in enumerate(cdgs):
        if len(cdg.es) > 0:
            assert(cdg.es[0]['cdg_num'] == cdg_i)

    vcs = []
    next_vc_cdgs = cdgs
    while len(next_vc_cdgs) > 0:
        # Build the CDG for the VC
        vc = build_cdg_vc_fas(A, next_vc_cdgs)

        # Get the feedback arc set, weighting each edge by the number of cdgs
        # that induce the edge.
        fas = vc.feedback_arc_set(weights='num_cdgs')

        # DEBUG
        #print 'fas:', fas

        # Find all the path CDGs that should be moved to the next VC
        removed_cdg_idxs = reduce(lambda x, y: x + y,
            map(lambda ie: vc.es[ie]['cdgs'], fas), [])

        # Remove the FAS
        vc.delete_edges(fas)

        # Add the VC to the list of VCs
        vcs.append(vc)

        #DEBUG
        #print 'removed_cdg_idxs:', removed_cdg_idxs
        print 'new vc.  Current #vcs:', len(vcs)

        # Update the loop variable
        next_vc_cdgs = map(lambda i: cdgs[i], removed_cdg_idxs)

    # All VCs CDGs must be DAGs
    assert(all(map(lambda vc: vc.is_dag(), vcs)))

    return vcs

def main():
    # Create the parser
    parser = argparse.ArgumentParser(
        description='Given forwarding tables, the number of VC\'s need to implement DFR.')

    # Forwarding model
    parser.add_argument('--model', default='plinko',
        choices=('plinko', 'eth-fcp'),
        help='Same meaning as resnet_alg.py.  Other choices are not '
        'supported.')

    # Use the feedback arc set (FAS) version of cycle breaking
    parser.add_argument('--fas', action='store_true',
        help='Whether to use the new Feedback Arc Set (FAS) cycle breaking ' \
            'algorithm')

    # The input topology
    parser.add_argument('topo', type=argparse.FileType('r'),
        help='The YAML for the generated topology. MUST be syntactically '
        'correct (e.g. the output from the topology generator (topo_gen.py)')

    # The files to parse
    parser.add_argument('tables', nargs='+', \
        help='The forwarding table YAML files.')

    # Parse the arguments
    args = parser.parse_args()

    #TODO: implement eth-fcp
    assert(args.model == 'plinko')

    # Parse the topology
    topo = yaml.load(args.topo, Loader=yaml.CLoader)
    switches = topo['Switches']
    G = build_graph(switches)
    V, E = G
    iG = mygraph_to_igraph(V, E)
    A = list(build_arcs(V))

    #print '|V|:', len(V)
    #print '|E|:', len(E)
    print '|A|:', len(A)

    # Parse and build the forwarding tables
    fwdtables = []
    for tfname in args.tables:
        with open(tfname) as tf:
            #table = yaml.load(tf, Loader=yaml.CLoader)
            #table = json.load(tf)
            #print 'Building a fwdtable...'
            fwdtable = build_fwdtable(V, E, tf, args)
            fwdtables.append(fwdtable)
    #random.shuffle(fwdtables)

    # Find all of the set of paths that are tied together into one backup route branching.
    pathCdgs = get_path_cdgs(fwdtables)

    # Assign the virtual channels to the CDGs
    if args.fas:
        vcs = assign_vcs_fas(A, pathCdgs)
    else:
        vcs = assign_vcs(A, pathCdgs)

    #DEBUG
    print 'vcs:', vcs

    print '|vcs|:', len(vcs)

    # TODO: looking at the path branching -> vc mapping may also be interesting
    # in addition to the total number of virtual channels

    #TODO: only paths that can be simultaneously in use at the same time can
    # cause cycles.  A path that uses an edge that another assumes is failed
    # cannot simultaneously be in used.  However, this is not true immediately
    # after a link fails.  Hmm...
    #TODO: The above property could be used to reduce the number of virtual
    # channels by reducing the number of cycles in the CDG, but doing so would
    # require some more theory about packet in flight safety.


if __name__ == "__main__":
    main()
