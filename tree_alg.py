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
import bitweave
import heapq
import itertools
import igraph
import ijson
import json
import myjsone
import math
import random
import scipy.stats
import scipy.misc
import socket
import yaml
from collections import deque
from yaml import CLoader as Loader, CDumper as Dumper

# Trick for accomplishing Enums in old python
def enum(**enums):
    return type('Enum', (), enums)

# String enums for argument parsing and checking
Models = enum(EDST = 'edst', ADST = 'adst')

TTGs = enum(UNSET = None, LINE = 'line', NORES = 'nores',
            MLAYER = 'mlayer', ALAYER = 'alayer', T = 'T',
            RAND = 'rand', MAXDAG = 'maxdag')

TTG_SORT = enum(PERF = 'perf', RES = 'res')

# Configure JSON output
#jsone = json.JSONEncoder(indent=2, separators=(', ', ': '))
jsone = myjsone.myJSONEncoder(indent=2, maxindent=3, separators=(', ', ': '))

#class Vertex(object):
class Vertex:
    def __init__(self, name):
        self.vnum = -1
        self.name = name
        self.numhosts = 0
        #self.hosts = []
        self.host_ports = {}
        self.ports = {}
        self.tot_ports = 0
        self.edges = {}
        self.edgeSet = set()
        # Fwd table is f(d, curr_tree, up_tree, up_e) ->
        # (out_p, marked_failed_trees)
        self.fwdtable = []
        self.nopkthdr_fwdtable = []
 
        # v -> portnums connected to v
        self.nbr_ports = {}

    def __repr__(self):
        return self.name
    def __len__(self):
        return len(self.name)

#class Edge(object):
class Edge:
    def __init__(self, v1, p1, v2, p2):
        self.enum = -1
        self.v1 = v1
        self.p1 = p1
        self.v2 = v2
        self.p2 = p2
        self.name = str((self.v1, self.p1, self.v2, self.p2))

    def get_other(self, v, p):
        if (self.v1, self.p1) == (v, p):
            return (self.v2, self.p2)
        elif (self.v2, self.p2) == (v, p):
            return (self.v1, self.p1)
        else:
            raise ValueError

    def __repr__(self):
        return self.name

#class Path(object):
class Path:
    #dstPathIds = {}
    ##newid = itertools.count().next
    ##Path.newid()
    def __init__(self, v, path, failedE = set(), rPath = [], failedV = set()):
        self.v = v
        if path is not None and len(path) > 0:
            self.path = tuple(path)
            self.rv, self.rpath = reverse_path(v, path)
            self.dst = self.rv
            #if self.dst not in Path.dstPathIds:
            #    Path.dstPathIds[self.dst] = itertools.count().next
            #    Path.dstPathIds[self.dst]()
            #self.dstPid = Path.dstPathIds[self.dst]()
            #assert(self.dstPid > 0)
        else:
            if path is not None:
                self.path = tuple()
            else:
                self.path = None
            self.rv, self.rpath = None, None
            self.dst, self.dstPid = None, -1
        self.failedE = failedE
        self.failedV = failedV
        self.extraRPath = rPath
        self.newpath = None

        self.edges, self.vertices = set(), set()
        currv = v
        self.vertices.add(currv)
        if path is not None:
            for hop in path:
                self.edges.add(currv.edges[hop])
                currv = currv.ports[hop]
                self.vertices.add(currv)

    def __repr__(self):
        return str((self.v, self.path))

def reverse_path(src, path):
    revpath = []
    v = src
    for hop in path:
        e = v.edges[hop]
        nextv, revhop = e.get_other(v, hop)
        revpath.append(revhop)
        v = nextv
    revpath.reverse()
    return v, revpath

def revpath_at_fail(path, edges):
    revpath = []
    v = path.v
    for hop in path.path:
        e = v.edges[hop]
        if e in edges:
            revpath.reverse()
            return v, revpath
        nextv, revhop = e.get_other(v, hop)
        revpath.append(revhop)
        v = nextv
    #Allow for no edges to be failed out of convenience
    #raise ValueError
    revpath.reverse()
    return v, revpath

def is_host(str):
    if str.startswith('host'):
        return True
    try:
        socket.inet_aton(str)
        return True
    except socket.error:
        return False

def build_graph(switches):
    V, E = set(), set()
    nameToV, verticesToE = {}, {}

    # Helper functions
    def get_vertex(sname):
        if sname in nameToV:
            return nameToV[sname]
        else:
            v = Vertex(sname)
            V.add(v)
            nameToV[sname] = v
            return v
    def get_edge(v1, p1, v2, p2):
        if (v1, p1, v2, p2) in verticesToE:
            return verticesToE[(v1, p1, v2, p2)]
        elif (v2, p2, v1, p1) in verticesToE:
            return verticesToE[(v2, p2, v1, p1)]
        else:
            e = Edge(v1, p1, v2, p2)
            E.add(e)
            verticesToE[(v1, p1, v2, p2)] = e
            return e

    # Read the topology
    for sw in switches:
        sname = sw.keys()[0]
        v = get_vertex(sname)
        ports = sw.values()[0]['ports']
        for port, portstr in ports.iteritems():
            v.tot_ports += 1
            portstr = portstr.split(' ')
            dev = portstr[0]
            otherp = int(portstr[-1])
            if not is_host(dev):
                otherv = get_vertex(dev)
                e = get_edge(v, port, otherv, otherp)
                v.ports[port] = otherv
                if otherv not in v.nbr_ports:
                    v.nbr_ports[otherv] = []
                v.nbr_ports[otherv].append(port)
                v.edges[port] = e
                v.edgeSet.add(e)
                otherv.ports[otherp] = v
                otherv.edges[otherp] = e
            else:
                v.host_ports[port] = dev
                #v.hosts.append(dev)
                v.numhosts += 1

    # Number the vertices and edges
    Vlist, Elist = list(V), list(E)
    Vlist.sort(lambda x, y: cmp(x.name, y.name))
    Elist.sort(lambda x, y: cmp(x.name, y.name))
    for i, v in enumerate(Vlist):
        v.vnum = i
    for i, e in enumerate(Elist):
        e.enum = i

    #for v in Vlist:
    #    print '%s: %d' % (v.name, v.vnum)
    #for e in Elist:
    #    print '%s: %d' % (str(e), e.enum)

    # Freeze the edgeSets
    for v in V:
        v.edgeSet = frozenset(v.edgeSet)

    # If there are no hosts, then everybody has one host
    if all(map(lambda v: v.numhosts == 0, V)):
        for v in V:
            v.numhosts += 1

    return V, E

def copy_graph(V, E):
    pass

def build_init_paths(V, d, iG):
    for v in V:
        if v.numhosts > 0:
            vigid = v.igid # Init paths have no failures, so this is correct
            digid = d.igid
            assert(iG.vs[vigid]['name'] == v)
            assert(iG.vs[digid]['name'] == d)
            iP = iG.get_shortest_paths(vigid, digid, output='epath')
            iP = iP[0] # Silly double list
            if len(iP) > 0:
                hoplist = igraph_path_to_hoplist(v, d, iP, iG)
                #print v, vigid, d, digid
                #print v, '->', d, hoplist
                if len(hoplist) > 0:
                    v.path = Path(v, hoplist)
                else:
                    v.path = Path(v, None)
            else:
                v.path = Path(v, None)
        else:
            v.path = Path(v, None)

def shortest_path(V, E, iG, src, dst, failedE = set(), extraRevPath = [], failedV = set(), fail = 'edges'):
    if src == dst:
        return Path(src, None, failedE, extraRevPath, failedV)
    assert(dst.numhosts > 0)

    if iG == None:
        return Path(src, None, failedE, extraRevPath, failedV)

    if fail == 'vertices' and dst in failedV:
        return Path(src, None, failedE, extraRevPath, failedV)

    if not iG.is_directed():
        sub_iG = iG
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

    #print 'sub_iG:', sub_iG
    #print 'sub_iG.vs:', [v['name'] for v in sub_iG.vs]
    #print 'src:', src
    #print 'dst:', dst
    #print 'failedE:', failedE

    # Get the new subgraph src and dst ids
    try:
        srcid = sub_iG.vs.find(name=src).index
        dstid = sub_iG.vs.find(name=dst).index
    except ValueError:
        return Path(src, None, failedE, extraRevPath, failedV)

    # Compute the path
    iP = sub_iG.get_shortest_paths(srcid, dstid, output='epath')
    iP = iP[0] # Silly double list
    #print 'iP:', iP
    if len(iP) == 0:
        return Path(src, None, failedE, extraRevPath, failedV)
    else:
        hoplist = igraph_path_to_hoplist(src, dst, iP, sub_iG)
        if len(hoplist) == 0:
            hostplist = None
    newpath = Path(src, hoplist, failedE, extraRevPath, failedV)

    return newpath

def mygraph_to_igraph(V, E):
    iG = igraph.Graph()
    #vnames = [v.name for v in V]
    vs = list(V)
    iG.add_vertices(vs)
    for iV in iG.vs:
        iV['name'].igid = iV.index
    #for v in V:
    #    v.igid = iG.vs.find(name=v).index
    for e in E:
        iG.add_edge(e.v1.igid, e.v2.igid, name=e)
        #e.igid = iG.es.find(name=e).index
    for iE in iG.es:
        iE['name'].igid = iE.index
    return iG

def igraph_path_to_hoplist(v, dst, iP, iG):
    hoplist = []
    currv = v
    #print 'iP:', iP
    for eigid in iP:
        e = iG.es[eigid]['name']
        #print 'currv:', currv
        #print 'e:', e
        #print
        if currv is e.v1:
            hop = e.p1
            currv = e.v2
        elif currv is e.v2:
            hop = e.p2
            currv = e.v1
        else:
            print 'currv:', currv
            print 'e:', e
            raise ValueError("Bad edge")
        hoplist.append(hop)
    assert(currv == dst)
    return hoplist

#XXX: This is a huge mess.
def build_default_tree(V, E, iG, dst):

    # Get the parents in the BFS search
    try:
        dstid = iG.vs.find(name=dst).index
    except ValueError:
        return None
        
    ret = iG.bfs(dstid)
    visited, parents = ret[0], ret[2]
    #print 'dstid:', dstid
    ##print 'visited:', visited
    #print 'parents:', parents

    # Build a tree
    iT = igraph.Graph()
    iT.to_directed()

    # Add the vertices
    #vs = [iG.vs[igid]['name'] for igid in visited]
    vs = iG.vs
    vnames = [v['name'] for v in vs]
    #print 'vs:', vs
    vids = [v.index for v in vs]
    pc = [(parents[i], c) for i, c in enumerate(vids)]
    iT.add_vertices(vnames)
    iTvids = {v['name']: v.index for v in iT.vs}

    # Add the edges
    edge_map = {}
    for old_pid, old_cid in pc:
        #print 'old_pid:', old_pid
        #print 'old_cid:', old_cid
        if old_cid == dstid or old_pid < 0:
            continue
        p, c = vs[old_pid]['name'], vs[old_cid]['name']
        #print c, '->', p
        #pid = iT.vs.find(name=p).index
        #cid = iT.vs.find(name=c).index
        pid = iTvids[p]
        cid = iTvids[c]
        edge_opts = []
        for port in c.nbr_ports[p]:
            e = c.edges[port]
            edge_opts.append(e)
        e = random.choice(edge_opts)
        #assert(e.v1 == p or e.v2 == p)
        #assert(e.v1 == c or e.v2 == c)
        edge_map[(pid, cid)] = e
    iT.add_edges(edge_map.iterkeys())
    for iE in iT.es:
        iE['name'] = edge_map[iE.tuple]
    #print 'iT:', iT
    return iT

def edst_tree(G, iG, dst, availE):
    V, E = G

    # Get the set of all possible edges to consider
    eSet = set(availE)
    pickedE = set()

    # Init the number of edges per node
    edgesAtNode = {v: 0 for v in V}

    #########################################
    # Helper functions for disjoint sets
    #########################################
    def djs_make_set(x):
        x._parent = x
        x._rank   = 0
        x._es     = set()

    def djs_union(x, y, e):
        xRoot = djs_find(x)
        yRoot = djs_find(y)
        if xRoot._rank > yRoot._rank:
            yRoot._parent = xRoot
            newRoot = xRoot
        elif xRoot._rank < yRoot._rank:
            xRoot._parent = yRoot
            newRoot = yRoot
        # Unless x and y are already in same set, merge them
        elif xRoot != yRoot: 
            yRoot._parent = xRoot
            xRoot._rank = xRoot._rank + 1
            newRoot = xRoot

        # Add the edges that connect the component
        es = (xRoot._es | yRoot._es)
        es.add(e)
        newRoot._es = es

    def djs_find(x):
        if x._parent == x:
            return x
        else:
            x._parent = djs_find(x._parent)
            return x._parent

    def djs_es(x):
        return djs_find(x)._es

    # Build a set of connected components, with each node initially
    # isolated and each partition containing no edges
    map(djs_make_set, V)

    # Randomly select edges to merge compontents until there are no more edges
    # or we have a connected tree
    usedEdgeCount = 0
    while usedEdgeCount < (len(V) - 1) and len(eSet) > 0:
        e = random.choice(tuple(eSet))

        # Bias against picking many edges at same node
        tryCount = 0;
        while (edgesAtNode[e.v1] > 2 or edgesAtNode[e.v2] > 2) and tryCount < 5:
                tryCount += 1
                e = random.choice(tuple(eSet))

        # Find the endpoints
        v1, v2 = e.v1, e.v2

        # Connect the endpoints if they are not already connected
        if djs_find(v1) is not djs_find(v2):
            # Update the edge usage
            availE.remove(e)
            pickedE.add(e)
            usedEdgeCount += 1
            edgesAtNode[v1] += 1
            edgesAtNode[v2] += 1

            # Merge the vertex components
            djs_union(v1, v2, e)

        # Remove the considered edge regardless of whether it was used
        # because it will not be useful
        eSet.remove(e)

    # TODO: partial trees!

    if usedEdgeCount < (len(V) - 1):
        #DEBUG
        #print 'Partial tree!'

        if dst is not None:
            treeE = djs_es(dst)

            #DEBUG
            #print 'dst partition: ', treeE

            #TODO: Return unused edges to availE if we are building multiple disjoint sets
        else:
            treeE = pickedE
        return None
        """
        if len(dstDJ) > 1:
        dstDJ = vertDJ[dst]
        print 'edst_tree: Usable partial tree'
        print dstDJ
        """
    else:
        if dst is not None:
            dstRoot = djs_find(dst)
        else:
            # Pick any partition, they are all the same
            dstRoot = djs_find(V.__iter__().next())
        treeE = dstRoot._es
        #print 'dst partition: ', treeE
        assert(len(treeE) == len(V) - 1)
        assert(all(map(lambda v: djs_find(v) == dstRoot, V)))

    # Build the igraph tree for returning
    eigids = [e.igid for e in treeE]
    iT = iG.subgraph_edges(eigids, delete_vertices=False)

    return iT

def edst_forest(G, iG, dst, num_trees = 0, quit_early = False):
    # Trivial solution
    if quit_early and num_trees == 0:
        return []

    V, E = G
    forest = []
    availE = set(E)
    tree = edst_tree(G, iG, dst, availE)
    while tree is not None:
        forest.append(tree)
        if quit_early and len(forest) >= num_trees:
            break
        tree = edst_tree(G, iG, dst, availE)

    return forest

def igraph_connectivity(iG, dstid):
    # XXX: Would be better to solve these simultaneously as originally
    # described, but it seems fast enough for now
    connectivity = iG.ecount()
    for iv in iG.vs:
        if iv.index != dstid:
            new_connectivity = iG.edge_connectivity(source=dstid, target=iv.index)
            connectivity = min(connectivity, new_connectivity)

    return connectivity

"""
Compute the minimum number of edges that, if frmoved from G-T (iDG), would make
y neither reachable from x, nor from r.  Function is described in the Yossi
Shiloach '78 publication "Edge-Disjoint Branching in Directed Multigraphs".

In order to check whether c_(G-T)((x, r) -> y) >= k or not, we add an auxiliary
vertex s to G-T together with two edges s -> x and s -> r, and assign infinite
capacity to each of these edges and one unit capacity to any other edge of G-T.
"""
def adst_maxflow_x_r_to_y(iDG, x, r, y):
    iG = iDG.copy()
    iG.add_vertex('s')
    s = iG.vs.find(name='s').index

    #DEBUG
    #print 'x: %d, r: %d, y: %d, s:, %d' % (x, r, y, s)

    #XXX: Sanity check that igraph is not changing old indices
    assert(iG.vs[x]['name'] == iDG.vs[x]['name'])
    assert(iG.vs[r]['name'] == iDG.vs[r]['name'])
    assert(iG.vs[y]['name'] == iDG.vs[y]['name'])

    # Add the new edges
    iG.add_edge(s, x, name='s2x')
    s2x = iG.es.find(name='s2x').index
    iG.add_edge(s, r, name='s2r')
    s2r = iG.es.find(name='s2r').index

    # Set the capacities
    iG.es['capacity'] = 1
    iG.es[s2x]['capacity'] = 1000 * len(iG.es) # Infinity
    iG.es[s2r]['capacity'] = 1000 * len(iG.es) # Infinity
    #print iG.es['capacity']

    maxflow = iG.maxflow(s, y, capacity='capacity')

    return maxflow

def adst_tree(G, iDG, dst, k):
    # Find the destination
    ir = iDG.vs.find(name=dst).index

    # Initialize iT
    iT = igraph.Graph(directed=True)
    iT.add_vertex(dst)

    # Initialize helper sets of vertices in the tree
    v_T = set([dst])
    iv_T = set([ir])
    iV = set([v.index for v in iDG.vs])

    # Helper function for finding the frontier
    def is_frontier(ie):
        return ie.source in iv_T and ie.target not in iv_T

    # Initialize the frontier
    #es_DG = iDG.es
    #frontier = set([es_DG[e] for e in iDG.incident(dst_DG)])

    while v_T != G[0]:
        # Select the frontier edges each time.
        #XXX: Although this is more time expensive than incrementally computing
        # the frontier, deleting edges from a graph in igraph mutates the edge
        # indexes and does not update existing edge references, so I don't see
        # any better solution.
        frontier = iDG.es.select(is_frontier)

        #TODO: I'm not sure why this sometimes doesn't hold.
        # Let's see if it is a problem.
        #assert(len(frontier) > 0)
        if len(frontier) == 0:
            return None

        #DEBUG
        #print 'dst_DG:', dst_DG
        #print 'frontier:', frontier, 'len:', len(frontier)
        #for ie in frontier:
        #    print 'ie:', ie, ie.source, ie.target

        # Choose an edge from the frontier
        ie = random.choice(frontier)
        ix, iy = ie.source, ie.target # y is the destination of the edge
        assert(ix in iv_T and iy not in iv_T)

        #DEBUG:
        #print 'ie:', ie
        #print 'ie: %d -> %d' % (ix, iy)

        # Compute a maxflow/mincut of (x, r) -> y
        maxflow = adst_maxflow_x_r_to_y(iDG, ix, ir, iy)

        #TODO: I'm not sure why this sometimes doesn't hold.
        # Let's see if it is a problem.
        #assert(maxflow.value >= k - 1)
        if maxflow.value < k - 1:
            return None

        #DEBUG:
        #print 'maxflow:', maxflow
        #print 'value:', maxflow.value
        #print 'cut:', maxflow.cut
        #print 'partition:', maxflow.partition
        #print dir(maxflow)

        # Find a new e' because of not enough flow
        if maxflow.value < k:
            assert(len(maxflow.partition) == 2)
            part = (set(maxflow.partition[0]), set(maxflow.partition[1]))
            if iy in part[1]:
                A, B = part[0], part[1]
            else:
                A, B = part[1], part[0]
            s = maxflow.graph.vs.find(name='s')
            assert(s.index in A)
            assert(ir in A)

            # Define a function to select a new eprime
            def is_eprime(ie):
                return ie.source in (iv_T - A) and ie.target in (iV - iv_T) - A

            # Select the eprimes, one of which must exist
            eprimes = iDG.es.select(is_eprime)

            #TODO: I'm not sure why this sometimes doesn't hold.
            # Let's see if it is a problem.
            if len(eprimes) == 0:
                return None
            #assert(len(eprimes) > 0)

            # Select a random eprime and set ie, ix, and iy
            ie = random.choice(eprimes)
            ix, iy = ie.source, ie.target # y is the destination of the edge

            #DEBUG:
            #print 'new ie:', ie
            #print 'new ie: %d -> %d' % (ix, iy)

            #DEBUG: Verify that the connectivity holds as expected
            iDG_tmp = iDG.copy()
            iDG_tmp.delete_edges(ie.index) 
            #tmp_connectivity = igraph_connectivity(iDG_tmp, ir)
            #print 'tmp_connectivity:', tmp_connectivity, 'k-1:', k-1

            #TODO: I'm not sure why this sometimes doesn't hold
            #assert(igraph_connectivity(iDG_tmp, ir) == (k - 1))

        # Update the tree and graph
        x, y = iDG.vs[ix]['name'], iDG.vs[iy]['name']
        #print 'y:', y, y.ports
        iT.add_vertex(y)
        #XXX: igraph doesn't return the new vertex id upon adding, so I
        # have to find it immediately after adding it
        iT_x = iT.vs.find(name=x)
        iT_y = iT.vs.find(name=y)
        #print 'iT_y:', iT_y
        v_T.add(y)
        iv_T.add(iy)
        e = ie['name']
        iDG.delete_edges(ie.index)
        #XXX: Because we do not add the edge backwards, so we get a branching,
        # not a tree.  However, this turns out to be correct because
        # iT.get_shortest_paths in forest_paths finds paths from the
        # destination, which are then reversed.
        iT.add_edge(iT_x.index, iT_y.index, name=e) 

    return iT

"""
Compute ADST as described by the Yossi Shiloach '78 publication
"Edge-Disjoint Branching in Directed Multigraphs", where edge-disjoint
on the bi-directed graph equivalent of iG is eqaul to arc-disjoint
NOTE: As originally described, I create a dst-branching, not a dst-rooted
tree. A simple link reversal of each tree will give the dst-rooted tree.
"""
def adst_forest(G, iG, dst, num_trees = 0, quit_early = False):
    V, E = G

    # Create a directed copy of the graph
    iDG = iG.copy()
    iDG.to_directed(mutual=True)
    #print iDG

    # Get the dst id
    dstid = iDG.vs.find(name=dst).index

    # Find the connectivity of the graph
    connectivity = igraph_connectivity(iDG, dstid)
    #print 'connectivity:', connectivity

    # Trivial solution
    if quit_early and num_trees == 0:
        return []

    # Build the forest one tree at a time
    forest = []
    for k in range(connectivity, 0, -1):
        #print 'k:', k
        iT = adst_tree(G, iDG, dst, k)

        # Allowing ADST to fail at the moment.
        #assert(iT != None)
        if iT == None:
            print 'failed to find tree.', 'connectivity:', connectivity, '|forest|', len(forest)
            return forest

        #print iT
        forest.append(iT)

        if quit_early and len(forest) >= num_trees:
            break

    return forest

def forest_paths(G, forest, dst):
    V, E = G

    forest_paths = {v: {} for v in V}

    for iT in forest:
        # Get the dst id
        dstid = iT.vs.find(name=dst).index

        # Get all of the shortest paths
        iPs = iT.get_shortest_paths(dstid, output='epath')

        for iv in iT.vs:
            v = iv['name']
            iP = iPs[iv.index]
            # XXX: Hack because igraph.OUT doesn't do anything for
            # iT.get_shortest_paths
            iP.reverse()
            if v == dst:
                hoplist = []
            elif len(iP) > 0:
                #print 'src:', v, 'dst:', dst
                #print 'edges:', [iT.es[ie]['name'] for ie in iP]
                hoplist = igraph_path_to_hoplist(v, dst, iP, iT)
                assert(len(hoplist) > 0)
            else:
                print 'No path from', v, 'to', dst
                assert(0)
                hoplist = None
            forest_paths[v][iT] = Path(v, hoplist)
            #print iv['name'], '-->', iPs[iv.index]

        #print iPs

    return forest_paths

#class IncAvg(object):
class IncAvg:
    def __init__(self):
        self.avg = 0
        self.i = 0

    def update(self, val):
        self.i += 1
        self.avg = (val - self.avg) / (1.0 * self.i) + self.avg

    def get(self):
        return self.avg

# All TTGs must add all of the vertices to a directed graph
def ttg_common(forest):
    # Create a directed graph
    ttg = igraph.Graph()
    ttg.to_directed()

    # Add each tree to the TTG and name them
    ttg.add_vertices(len(forest))
    assert (len(forest) == len(ttg.vs))
    for i in range(len(forest)):
        ttg.vs[i]['name'] = forest[i]['name']
        ttg.vs[i]['tree'] = forest[i]

    return ttg

def ttg_nores(forest):
    # Create a directed graph
    ttg = ttg_common(forest)

    # Mark all trees as the l1 trees
    for i in range(len(ttg.vs)):
        ttg.vs[i]['l1'] = True
    
    # No resilient DFR EDST has a TTG with no edges.
    # Thus, we are done.

    return ttg

def ttg_line(forest, num_trees):
    # Create a directed graph
    ttg = ttg_common(forest)

    # Add the edges for a line
    edges = [(i, i + 1) for i in range(len(forest) - 1)]
    ttg.add_edges(edges)

    # Mark the l1 tree(s)
    assert(len(ttg.vs[0].predecessors()) == 0)
    assert(num_trees != 0)
    if num_trees < 0:
        ttg.vs[0]['l1'] = True
        for i in range(1, len(ttg.vs)):
            ttg.vs[i]['l1'] = False
    else:
        assert(len(ttg.vs) >= num_trees)
        for i in range(len(ttg.vs) - num_trees + 1):
            ttg.vs[i]['l1'] = True
        for i in range(len(ttg.vs) - num_trees + 1, len(ttg.vs)):
            ttg.vs[i]['l1'] = False

    return ttg

def ttg_mred_layered_dag(forest, l1width, self_layer):
    # Helper function to find the number of trees in the next layer
    def mred_next_width_func(x):
        assert(type(x) == type(1))
        return int(round(x / 2.0)) if x > 1 else 1

    return ttg_layered_dag(forest, l1width, self_layer, mred_next_width_func)

def ttg_ared_layered_dag(forest, l1width, self_layer):
    # Helper function to find the number of trees in the next layer
    def ared_next_width_func(x):
        assert(type(x) == type(1))
        y = x - 2
        return y if y > 1 else 1

    return ttg_layered_dag(forest, l1width, self_layer, ared_next_width_func)

def ttg_t_layered_dag(forest, l1width, self_layer):
    # Helper function to find the number of trees in the next layer
    def t_next_width_func(x):
        assert(type(x) == type(1))
        return 1

    return ttg_layered_dag(forest, l1width, self_layer, t_next_width_func)

def ttg_layered_dag(forest, l1width, self_layer, next_width_func):
    # Create a directed graph
    ttg = ttg_common(forest)

    # Find out how many trees in each layer
    trees_per_layer = [l1width]
    while sum(trees_per_layer) < len(forest):
        trees_per_layer.append(next_width_func(trees_per_layer[-1]))
    if sum(trees_per_layer) > len(forest):
        trees_per_layer[-1] -= sum(trees_per_layer) - len(forest)
        assert(trees_per_layer[-1] > 0)
    assert(sum(trees_per_layer) == len(forest))

    # Assign the trees to the layers
    layers = [range(sum(trees_per_layer[0:i]), sum(trees_per_layer[0:i+1])) \
        for i in range(len(trees_per_layer))]

    #DEBUG: print the number of trees per layer
    #print 'trees_per_layer:', trees_per_layer
    #print 'layers:', layers

    # Some assertions of correctness
    for i in range(len(layers)):
        assert (len(layers[i]) == trees_per_layer[i])

    # Connect the layers
    edges = []
    for i in range(len(layers) - 1):
        new_edges = [(x, y) for x in layers[i] for y in layers[i+1]]
        edges.extend(new_edges)
    ttg.add_edges(edges)

    # Find the first layer 
    first_layer = [iT for iT in ttg.vs.select(lambda v: len(v.predecessors()) == 0)]
    first_layer = set(map(lambda ttgV: ttgV.index, first_layer))
    assert(len(first_layer) > 0)

    # Connect within the layers if requested
    if self_layer:
        self_edges = []
        for layer in layers:
            new_edges = [(layer[x], layer[x + 1]) for x in range(len(layer) - 1)]
            self_edges.extend(new_edges)
        ttg.add_edges(self_edges)

    # Label the layer-1 trees
    for ttgV in ttg.vs:
        if ttgV.index in first_layer:
            ttg.vs[ttgV.index]['l1'] = True
        else:
            ttg.vs[ttgV.index]['l1'] = False

    #DEBUG
    #print 'edges:', edges

    return ttg

def ttg_rand_dag(forest, rand_res):
    return ttg_rand_max_dag_common(forest, rand_res, ttg_rand_dag_helper)

def ttg_max_dag(forest, rand_res):
    # XXX: It is kinda coincidence that ttg_rand_dag_helper_opt alwasy
    # generates an adjacency graph has has ones in the upper triangle.
    return ttg_rand_max_dag_common(forest, rand_res, ttg_rand_dag_helper_opt)

def ttg_rand_max_dag_common(forest, rand_res, helper_func):

    assert(len(forest) > rand_res)

    # Create a directed graph
    ttg = ttg_common(forest)

    # Build a the layer-1 DAG
    if rand_res > 0:
        sub_forest = forest[:-rand_res]
    else:
        sub_forest = forest[:]
    helper_func(ttg, sub_forest)

    # DEBUG
    #print 'rand DAG edges:', len(ttg.es)
    #print ttg
    #print 'adjacency:'
    #print ttg.get_adjacency()

    # DEBUG
    assert(ttg.is_dag())
    assert(ttg.subgraph(range(len(sub_forest))).is_connected(igraph.WEAK))

    # Label the vertices for later
    for i in range(len(forest)):
        if i < len(forest) - rand_res:
            ttg.vs[i]['l1'] = True
            ttg.vs[i]['r'] = 0
        else:
            assert(len(ttg.vs[i].predecessors()) == 0 and \
                len(ttg.vs[i].successors()) == 0)
            ttg.vs[i]['l1'] = False
            ttg.vs[i]['r'] = i - (len(forest) - rand_res) + 1

    #DEBUG
    #for vs in ttg.vs:
    #    print vs, ', r:', vs['r']

    # Connect the extra vertices for resilience
    if rand_res > 0:
        ridx = len(forest) - rand_res
        assert(ttg.vs[ridx]['r'] == 1)
        res_edges = [(i, ridx) for i in range(ridx)]
        res_edges.extend([(i, i + 1) for i in range(ridx, len(forest) - 1)])
        ttg.add_edges(res_edges)

    #DEBUG
    #print ttg
    
    return ttg

def ttg_rand_dag_helper_opt(ttg, forest):

    # Create a fully connected graph
    edges = [(i, j) for i in range(len(forest)) for j in range(len(forest)) if i != j]
    ttg.add_edges(edges)

    # Find the feedback arc set
    #fas = ttg.feedback_arc_set(method = 'ip')
    fas = ttg.feedback_arc_set()

    # Remove the feedback arc set
    ttg.delete_edges(fas)

def ttg_rand_dag_helper(ttg, forest):

    # Create a fully connected graph
    edges = [(i, j) for i in range(len(forest)) for j in range(len(forest)) if i != j]
    ttg.add_edges(edges)

    # Randomly break cycles until the graph is acyclic
    while not ttg.is_dag():
        # DFS search
        ivs = [iv for iv in ttg.vs]
        random.shuffle(ivs)
        visited = {iv.index: False for iv in ivs}
        stack = [(iv, [iv.index], set((iv.index,))) for iv in ivs]
        while len(stack) > 0:
            iv, pv, spv = stack.pop()

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
                    ttg_rand_break_cycle(ttg, cycle)
                if visited[iw.index] == False:
                    stack.append((iw, pv + [iw.index], spv | set((iw.index,))))

def ttg_rand_break_cycle(ttg, cycle):

    # Building cycle_edges this way to allow for quitting early
    cycle_edges = []
    for i in range(len(cycle) - 1):
        #XXX: ttg.get_eids(cycle[i], cycle[i+1], error = False) should work in
        # this case because we do not have a multigraph
        x = filter(lambda x: ttg.es[x].target == cycle[i+1], ttg.incident(cycle[i]))
        # Return early if links don't actually exist
        if len(x) == 0:
            #print 'quitting early'
            return
        assert(len(x) == 1)
        cycle_edges.append(x[0])

    # Choose an edge randomly and remove it
    e = random.choice(cycle_edges)
    ttg.delete_edges([e])

def edst_fwdtable(G, forest, fpaths, ttg, dst, args):
    if args.dfr:
        assert(ttg != None)
        edst_fwdtable_dfr(G, forest, fpaths, ttg, dst, args)
    else:
        assert(ttg == None)
        edst_fwdtable_normal(G, forest, fpaths, dst, args)

def edst_fwdtable_dfr(G, forest, fpaths, ttg, dst, args):
    V, E = G

    # Unncessary asserts as they should already be asserted, but including
    # anyways
    assert(ttg != None)
    assert(len(forest) > 0)
    assert(len(forest) == len(ttg.vs))
    assert(ttg.is_dag())

    if args.num_trees > len(forest):
        assert (args.maxl1 > 0)
        sys.stderr.write('More trees are requested than exist!\n')
        #XXX: I could probably do better than this.
        args.num_trees = len(forest)
        #sys.exit(1)

    # Find the first layer 
    first_layer = [iT for iT in ttg.vs.select(lambda v: v['l1'] == True)]
    assert(len(first_layer) > 0)

    # Find the rest of the layers
    layers = []
    curr_layer = first_layer
    curr_layer_set = set(map(lambda iT: iT['name'], curr_layer))
    while len(curr_layer) > 0:
        layers.append(curr_layer)
        #Dict (name -> ttgV) because successors creates new ttgV
        # objects, but we guarantee that names are unique
        next_layer_dict = {}
        for iT in curr_layer:
            next_layer_dict.update({aiT['name']: aiT for aiT in iT.successors() if aiT['name'] not in curr_layer_set})
        curr_layer = next_layer_dict.values()
        curr_layer_set = set(map(lambda iT: iT['name'], curr_layer))

    #DEBUG
    layers_set = map(lambda layer: set(layer), layers)
    for i in range(len(layers_set)):
        for j in range(i + 1, len(layers_set)):
            assert(layers_set[i].isdisjoint(layers_set[j]))
    assert(sum(map(lambda layer: len(layer), layers)) == len(ttg.vs))

    # DEBUG:
    #print 'layers:', [[iT['name'] for iT in l] for l in layers]

    # Remove some of the trees if requested.  This must be done on a per-dst
    # basis because very vertex must use the same trees.
    assert (args.num_trees != 0)
    if args.num_trees > 0:
        # Compute the average distance to the dst from each vertex
        #TODO: this could be done better with fpaths than calling into igraph
        avg_layer_distance = []
        for layer in layers:
            for ttgV in layer:
                #pathlens = ttgV['tree'].shortest_paths(None, dst.igid)
                #avg_pathlen = 1.0 * reduce(lambda x, y: x + y[0], pathlens, 0) / len(pathlens)
                pathlens = [len(fpaths[v][ttgV['tree']].path) for v in V]
                avg_pathlen = 1.0 * sum(pathlens) / len(pathlens)
                avg_layer_distance.append((ttgV, avg_pathlen))

                #DEBUG
                #print ttgV['name'], ':', avg_pathlen

        # Find the, on average, shortest trees for this destination
        avg_layer_distance.sort(lambda x, y: cmp(x[1], y[1]))
        top_trees = set([x[0] for x in avg_layer_distance[:args.num_trees]])

        #DEBUG
        #print 'avg_layer_distance:', [(x[0]['name'], x[1]) for x in avg_layer_distance]
        #print 'top_trees:', [x['name'] for x in top_trees]
        #print 'layer[0]:', [x['name'] for x in layers[0]]

        # Hack for RAND TTG
        if args.ttg_type == TTGs.RAND or args.ttg_type == TTGs.MAXDAG:
            args.maxl1 = args.num_trees - args.rand_res
            assert(args.maxl1 > 0)
        # Hack for improved line
        if args.ttg_type == TTGs.LINE:
            args.maxl1 = args.num_trees

        # Restrict the number of trees in the first layer to maxl1
        avg_layer_distance_d = {x[0]: x[1] for x in avg_layer_distance}
        next_tree = args.num_trees
        l0trees = list(top_trees & set(layers[0]))
        while len(l0trees) > args.maxl1 and next_tree < len(forest):
            badt = reduce(lambda x, y: x if avg_layer_distance_d[x] > avg_layer_distance_d[y] else y, l0trees)
            newt = avg_layer_distance[next_tree][0]

            # Only perform the swapping if newt is not also in the first layer
            if newt not in set(layers[0]):
                top_trees.remove(badt)
                top_trees.add(newt)
            
                #DEBUG:
                #print 'removing tree %s and adding tree %s for performance' % (badt['name'], newt['name'])

            next_tree += 1
            l0trees = list(top_trees & set(layers[0]))
            
        #DEBUG
        #print 'new top_trees:', [x['name'] for x in top_trees]

        nlayers = []
        for layer in layers:
            nlayer = [ttgV for ttgV in layer if ttgV in top_trees]
            if len(nlayer) > 0:
                nlayers.append(nlayer)
        assert(len(nlayers) > 0)
        layers = nlayers

        # Hack for the new TTGs.LINE
        if args.ttg_type == TTGs.LINE and len(layers[0]) > 1:
            tmp_ts = reduce(lambda x, y: x + y, layers)
            tmp_ts.sort(key=lambda x: x.index)
            layers = [[x] for x in tmp_ts]

        # Assert that the trees necessary for resilience are present given
        # TTGs.RAND
        if args.ttg_type == TTGs.RAND or args.ttg_type == TTGs.MAXDAG:
            assert(len(layers) == args.rand_res + 1)
            for _li, layer in enumerate(layers):
                assert(all(map(lambda ttgV: ttgV['r'] == _li, layer)))
                if _li > 0:
                    assert(len(layer) == 1)
                else:
                    assert(len(layer) == args.num_trees - args.rand_res)
        if args.ttg_type == TTGs.LINE:
            assert(all(map(lambda layer: len(layer) == 1, layers)))

    # DEBUG:
    #print 'layers:', [[iT['name'] for iT in l] for l in layers]

    # Build the forwarding tables for each vertex while respecting a DFR tree
    # transition diagram
    for v in V:
        # Nothing to do if we are the destination
        if v == dst:
            continue

        if args.ttg_sort == TTG_SORT.PERF:
            # Find the distance from v to dst given each tree:
            layer_distance = {}
            for layer in layers:
                for ttgV in layer:
                    layer_distance[ttgV] = ttgV['tree'].shortest_paths(v.igid, dst.igid)[0][0]

            # Define a function for sorting trees within a layer
            def perf_sort_layer(ttgV1, ttgV2):
                return cmp(layer_distance[ttgV1], layer_distance[ttgV2])

            # Assign the sort function
            sort_layer = perf_sort_layer

        elif args.ttg_sort == TTG_SORT.RES:
            # Find the shortest paths in the TTG so we can sort based on a
            # partial order.  ttg.topological_sorting(), except this may be too
            # restrictive because it returns a total ordering, not a partial
            # ordering
            #XXX: In practice, it looks like ttg.topological_sorting() would've
            # been fine.
            #XXX: this could be done earlier, not here. "whatever".
            ttg_shortest_paths = ttg.shortest_paths()

            # Define a function for sorting trees based on their potential fault
            # tolerance.  Trees that are earlier in the topological ordering can
            # lead to greater fault tolerance.
            def res_sort_layer(ttgV1, ttgV2):
                # Necessary in a DAG
                assert (math.isinf(ttg_shortest_paths[ttgV1.index][ttgV2.index]) or \
                        math.isinf(ttg_shortest_paths[ttgV2.index][ttgV1.index]))

                # There is a path from V1 to V2, so V1 comes first in the
                # partial order
                if not math.isinf(ttg_shortest_paths[ttgV1.index][ttgV2.index]):
                    return -1
                # There is a path from V2 to V1, so V2 comes first in the
                # partial order
                elif not math.isinf(ttg_shortest_paths[ttgV2.index][ttgV1.index]):
                    return 1
                else:
                    return 0

            # Assign the sort function
            sort_layer = res_sort_layer

            # DEBUG
            #topo_sorting = ttg.topological_sorting()
            #leaf = topo_sorting[-1]
            #resilience = ttg.shortest_paths(target = leaf)
            #print 'topo_sorting:', topo_sorting
            #print 'resilience:', resilience
            #my_sorting = reduce(lambda x, y: x + y, layers)
            #my_sorting.sort(res_sort_layer)
            #print 'my sorting:', [ttgV.index for ttgV in my_sorting]
        else:
            assert(0)

        # Randomize the ordering within each layer for each vertex.
        # Or, rather, randomize then sort by distance to the destination
        # as an attempt at good performance.
        for layer in layers:
            random.shuffle(layer)
            layer.sort(sort_layer)

        # DEBUG
        #for layer in layers:
        #    print [(ttgV['name'], layer_distance[ttgV]) for ttgV in layer]

        # Add entries to go from no tree to the first layer of trees
        #XXX: I think I'll let tree_throughput.py handle this problem by
        # randomly choosing one of the first layer trees to retry with
        # in case all of the first layer trees are failed.
        #XXX: tree_thoughput.py is handling this because top-k definitely needs
        # access to all of the 8-layers, and this program currently only
        # generates the trees for one layer.  This was a poor design choice.
        for ttgV in layers[0]:
            iT = ttgV['tree']
            path = fpaths[v][iT]
            assert(len(path.path) > 0) # No partial trees for now
            port = path.path[0]
            e = v.edges[port]
            # (dst, curr_tree, up_tree, up_e) -> (out_p, marked_failed_trees)
            # No trees ever need to be marked as failed because no tree
            # bitfield is needed given DFR EDST
            key, value = (dst, None, iT, e), (port, frozenset())
            v.fwdtable.append((key, value))

        # Add transitions from one layer to the next
        for i in range(len(layers)):
            for ttgV in layers[i]:
                iT = ttgV['tree']

                #XXX: although I could randomize layers[i+1:],
                # I choose not to because they are sorted in order for this
                # destination.  If some trees are equal, there could be benefit
                # to randomizing and resorting.  If performance is not good, I
                # should go and do this

                # Get the successors
                potential_succ = reduce(lambda x, y: x + y, layers[i:], [])
                successors = [x for x in potential_succ if ttgV.index != x.index and not math.isinf(ttg.shortest_paths(ttgV.index, x.index)[0][0])]

                #TODO: This would be more general if all of the layers were
                # checked to make sure that the shortest path is not infinity.
                # It should work as is though, and this way should be faster.
                #successors = [x for x in layers[i] if ttgV.index != x.index and not math.isinf(ttg.shortest_paths(ttgV.index, x.index)[0][0])]
                #successors.extend(reduce(lambda x, y: x + y, layers[i+1:], []))

                # Add the default path, i.e., the path when there are no failures
                path = fpaths[v][iT]
                assert(len(path.path) > 0) # No partial trees for now
                port = path.path[0]
                e = v.edges[port]
                # (dst, curr_tree, up_tree, up_e) -> (out_p, marked_failed_trees)
                # No trees ever need to be marked as failed because no tree
                # bitfield is needed given DFR EDST
                key, value = (dst, iT, iT, e), (port, frozenset())
                v.fwdtable.append((key, value))

                # Find the in-bound edges for this tree
                inbound_E = [iT.es[_eigid]['name'] for _eigid in iT.incident(v.igid) if iT.es[_eigid]['name'] != e]
                inbound_E.append(None) # For the initial start on the tree

                # Build the fwdtable as if there were no extra packet headers
                for in_e in inbound_E:
                    nph_key, nph_value = (dst, in_e, iT, e), (port, frozenset())
                    v.nopkthdr_fwdtable.append((nph_key, nph_value))

                # Add the successor trees in (per-layer randomzied)
                # layer order
                for attgV in successors:
                    aiT = attgV['tree']

                    # Find the output edge
                    path = fpaths[v][aiT]
                    assert(len(path.path) > 0) # No partial trees for now
                    port = path.path[0]
                    e = v.edges[port]

                    # Actually add the tree to the forwarding table.
                    # (dst, curr_tree, up_tree, up_e) -> (out_p, marked_failed_trees)
                    # No trees ever need to be marked as failed because no tree
                    # bitfield is needed given DFR EDST.
                    key, value = (dst, iT, aiT, e), (port, frozenset())
                    v.fwdtable.append((key, value))

                    # Build the fwdtable as if there were no extra packet headers
                    for in_e in inbound_E:
                        nph_key, nph_value = (dst, in_e, aiT, e), (port, frozenset())
                        v.nopkthdr_fwdtable.append((nph_key, nph_value))

def edst_fwdtable_normal(G, forest, fpaths, dst, args):
    V, E = G
    
    #XXX: Now that we quit early, this is not necessary.  Lets just assert that we have the right number of trees.
    dtrees = [t for t in forest if t['default']]
    rtrees = [t for t in forest if not t['default']]
    assert(len(dtrees) == args.default_trees)
    #assert(args.num_trees != 0)
    if args.num_trees >= 0:
        assert(len(rtrees) == args.num_trees)
    elif args.num_trees != 0:
        assert(len(rtrees) > 0)

    # Build the forwarding tables for each vertex using shorter paths
    # first whenever possible
    for v in V:
        # Nothing to do if we are the destination
        if v == dst:
            continue

        #DEBUG
        #print 'v:', v

        # Sort the trees by pathlength
        shortest_iTs = rtrees[:]
        random.shuffle(shortest_iTs)
        def sort_iT(x, y):
            xpath, ypath = fpaths[v][x], fpaths[v][y]
            assert(xpath.path is not None and ypath.path is not None)
            return cmp(len(xpath.path), len(ypath.path))
        shortest_iTs.sort(sort_iT)

        # Add entries to go from no tree to any of the trees
        if len(dtrees) > 0:
            start_trees = dtrees
        else:
            start_trees = shortest_iTs
        for iT in start_trees:
            path = fpaths[v][iT]
            assert(len(path.path) > 0) # No partial trees for now
            port = path.path[0]
            e = v.edges[port]
            # (dst, curr_tree, up_tree, up_e) -> (out_p, marked_failed_trees)
            key, value = (dst, None, iT, e), (port, frozenset())
            v.fwdtable.append((key, value))

        #DEBUG
        #print 'shortest_iTs lens:', [len(fpaths[v][iT].path) for iT in shortest_iTs]

        # Installing in shorest_iT order so that run_throughput.py can
        # determine the default tree
        for iT in dtrees + shortest_iTs:
            # Mark if the trees have been used  identify the set of trees to be
            # marked as failed if a rule is used.
            used_iT = set()

            #DEBUG
            #print 'iT:', iT['index']

            # Add the default path, i.e., the path when there are no failures
            path = fpaths[v][iT]
            assert(len(path.path) > 0) # No partial trees for now
            port = path.path[0]
            e = v.edges[port]
            # (dst, curr_tree, up_tree, up_e) -> (out_p, marked_failed_trees)
            key, value = (dst, iT, iT, e), (port, frozenset(used_iT))
            v.fwdtable.append((key, value))
            used_iT.add(iT)

            # Add the trees to the forwarding table in sorted order
            for aiT in shortest_iTs:
                # This tree has already been used as an alternate tree
                if aiT in used_iT:
                    continue

                #DEBUG
                #print '\taiT:', aiT['index']

                # Normal tree forwarding
                path = fpaths[v][aiT]
                assert(len(path.path) > 0) # No partial trees for now
                port = path.path[0]
                e = v.edges[port]

                # Actually add the tree to the forwarding table.
                # (dst, curr_tree, up_tree, up_e) -> (out_p, marked_failed_trees)
                key, value = (dst, iT, aiT, e), (port, frozenset(used_iT))
                v.fwdtable.append((key, value))
                used_iT.add(aiT)

def adst_fwdtable(G, forest, fpaths, dst, args):
    V, E = G

    #XXX: Now that we quit early, this is not necessary.  Lets just assert that we have the right number of trees.
    dtrees = [t for t in forest if t['default']]
    rtrees = [t for t in forest if not t['default']]
    assert(len(dtrees) == args.default_trees)
    #assert(args.num_trees != 0)
    if args.num_trees >= 0:
        assert(len(rtrees) == args.num_trees)
    elif args.num_trees != 0:
        assert(len(rtrees) > 0)

    # Create a mapping from arcs -> iT
    arc2tree = {}
    for iT in rtrees:
        for ie in iT.es:
            e = ie['name']
            # Target, not source, because iT is actually a branching
            v = iT.vs[ie.target]['name']
            assert((v, e) not in arc2tree) # No multiply used arcs
            arc2tree[(v, e)] = iT

    # Build the forwarding tables for each vertex using shorter paths
    # first whenever possible
    for v in V:
        # Nothing to do if we are the destination
        if v == dst:
            continue

        #DEBUG
        #print 'v:', v

        # Sort the resilient trees by pathlength
        shortest_iTs = rtrees[:]
        random.shuffle(shortest_iTs)
        def sort_iT(x, y):
            xpath, ypath = fpaths[v][x], fpaths[v][y]
            assert(xpath.path is not None and ypath.path is not None)
            return cmp(len(xpath.path), len(ypath.path))
        shortest_iTs.sort(sort_iT)

        #DEBUG
        #print 'shortest_iTs lens:', [len(fpaths[v][iT].path) for iT in shortest_iTs]

        # Add entries to go from no tree to any of the trees
        if len(dtrees) > 0:
            start_trees = dtrees
        else:
            start_trees = shortest_iTs
        for iT in start_trees:
            path = fpaths[v][iT]
            assert(len(path.path) > 0) # No partial trees for now
            port = path.path[0]
            e = v.edges[port]
            # (dst, curr_tree, up_tree, up_e) -> (out_p, marked_failed_trees)
            key, value = (dst, None, iT, e), (port, frozenset())
            v.fwdtable.append((key, value))

        for iT in dtrees + shortest_iTs:
            # Mark if the trees have been used already because of alternate
            # trees.  This is also used to identify the set of trees to be
            # marked as failed if a rule is used.
            used_iT = set()

            #DEBUG
            #print 'iT:', iT['index']

            # Add the default path, i.e., the path when there are no failures
            path = fpaths[v][iT]
            assert(len(path.path) > 0) # No partial trees for now
            port = path.path[0]
            e = v.edges[port]
            # (dst, curr_tree, up_tree, up_e) -> (out_p, marked_failed_trees)
            key, value = (dst, iT, iT, e), (port, frozenset(used_iT))
            v.fwdtable.append((key, value))
            used_iT.add(iT)

            # Find the reverse tree, i.e., the tree that uses the
            # opposite arc of the normal tree.  Reverse trees are not
            # guaranteed to exist.
            ov, op = e.get_other(v, port)
            if (ov, e) in arc2tree and arc2tree[ov, e] not in used_iT:
                aiT = arc2tree[ov, e]

                #DEBUG
                #print '\traiT:', aiT['index']

                # Reverse tree forwarding
                path = fpaths[v][aiT]
                assert(len(path.path) > 0) # No partial trees for now
                port = path.path[0]
                e = v.edges[port]

                # Actually add the tree to the forwarding table.
                # (dst, curr_tree, up_tree, up_e) -> (out_p, marked_failed_trees)
                key, value = (dst, iT, aiT, e), (port, frozenset(used_iT))
                v.fwdtable.append((key, value))
                used_iT.add(aiT)

            # Add the resilient trees to the forwarding table in sorted order
            for aiT in shortest_iTs:
                # This tree has already been used as an alternate tree
                if aiT in used_iT:
                    continue

                #DEBUG
                #print '\taiT:', aiT['index']

                # Normal tree forwarding
                path = fpaths[v][aiT]
                assert(len(path.path) > 0) # No partial trees for now
                port = path.path[0]
                e = v.edges[port]

                # Actually add the tree to the forwarding table.
                # (dst, curr_tree, up_tree, up_e) -> (out_p, marked_failed_trees)
                key, value = (dst, iT, aiT, e), (port, frozenset(used_iT))
                v.fwdtable.append((key, value))
                used_iT.add(aiT)

                # Find the reverse tree, i.e., the tree that uses the
                # opposite arc of the normal tree.  Reverse trees are not
                # guaranteed to exist.
                ov, op = e.get_other(v, port)
                if (ov, e) in arc2tree and arc2tree[ov, e] not in used_iT:
                    aiT = arc2tree[ov, e]

                    #DEBUG
                    #print '\traiT:', aiT['index']

                    # Reverse tree forwarding
                    path = fpaths[v][aiT]
                    assert(len(path.path) > 0) # No partial trees for now
                    port = path.path[0]
                    e = v.edges[port]

                    # Actually add the tree to the forwarding table.
                    # (dst, curr_tree, up_tree, up_e) -> (out_p, marked_failed_trees)
                    key, value = (dst, iT, aiT, e), (port, frozenset(used_iT))
                    v.fwdtable.append((key, value))
                    used_iT.add(aiT)

def number_trees(forest):
    # Number and name the trees, leaving 0 as a reserved value
    # representing a packet currently on no tree
    for i, iT in enumerate(forest):
        j = i + 1
        iT['index'] = j
        iT['name'] = 'tree_%d' % j

def print_fwdtable(fwdtable):
    for key, value in fwdtable:
        dst, iT, aiT, e = key
        port, mark_failed = value
        iTi = 0 if iT == None else iT['index']
        print '   ', dst, iTi, aiT['index'], e, '-->', port, [_iT['index'] for _iT in mark_failed]

def main():
    # Create the parser and subparsers
    parser = argparse.ArgumentParser(
        description='Given a topology, compute state requirements assuming '
        'one of many different resilient spanning tree routing algorithms')

    # Forwarding model
    parser.add_argument('--model', required=True,
        choices=(Models.EDST, Models.ADST),
        help='The forwarding model to use. ' + Models.EDST + ' is for '
        'edge-disjoint trees and ' + Models.ADST + ' is for arc-disjoint trees.')

    # Optionally accept a number of rounds to run for
    parser.add_argument('--default-trees', default=0, type=int,
        help='The number of non-resilient default trees to use')

    # Enable deadlock-free routing (DFR) - Requires EDST at the moment
    parser.add_argument('-d', '--dfr', action='store_true',
        help='Whether the routes should be deadlock-free or not. Current requires EDST.')

    # Just print the maximum number of trees
    parser.add_argument('-m', '--max-trees', action='store_true',
        help='If true, the number of trees will be printed and the program will exit early.')

    # Determine the TTG type
    parser.add_argument('-t', '--ttg-type', default = TTGs.UNSET,
        choices=(TTGs.LINE, TTGs.NORES, TTGs.MLAYER, TTGs.ALAYER, TTGs.T,
            TTGs.RAND, TTGs.MAXDAG),
        help='What graph type to use as a DFR tree transition diagram.\n '
        '\t' + TTGs.LINE + ': a line graph. \n'
        '\t' + TTGs.NORES + ': a disconnected graph (a la INFOCOM \'14). \n'
        '\t' + TTGs.MLAYER + ': a DAG where each layers are fully connected '
        'but reduce multiplicatively in the width of each layer (by a factor of 2). \n'
        '\t' + TTGs.ALAYER + ': a DAG where each layers are fully connected '
        'but reduce additively in the width of each layer (by a reducing by 2). \n'
        '\t' + TTGs.T + ': wide followed by 1s. Wide base, then as skinny as possible.\n'
        '\t' + TTGs.RAND + ': start with a fully connected graph and randomly remove edges, then add guaranteed resilience.\n'
        '\t' + TTGs.MAXDAG + ': start with a maximal DAG (upper triangle of adjacency matrix is all 1s.\n'
    )

    # Determine the TTG sorting
    parser.add_argument('--ttg-sort', default = TTG_SORT.PERF,
        choices=(TTG_SORT.PERF, TTG_SORT.RES),
        help='How should the order of trees i nthe forwarding table be decided.\n '
        '\t' + TTG_SORT.PERF + ': Orders based on shortest distance to the destination. \n'
        '\t' + TTG_SORT.RES + ': Orders based on fault tolerance (location in the TTG). \n'
    )

    # Optionally accept a level of resilience to limit forwarding table state
    parser.add_argument('-n', '--num-trees', default=-1, type=int,
        help='Optionally limit the number of trees in case there are too many trees')

    # Get the width of the first layer for some of the TTGs
    parser.add_argument('--l1width', default=0, type=int,
        help='The number trees to use in the base layer of the TTG')

    # Get the restricted width of the first layer of the TTGs
    parser.add_argument('--maxl1', default=-1, type=int,
        help='If the number of trees is limited, this argument sets the ' \
        'attempted maximum number of trees to allow to be in layer-1')

    # Connect all trees within a layer
    parser.add_argument('--self-layer', action='store_true',
        help='For MLayer, ALayer, and T, whether the trees within a ' \
        'layer are connected')

    # Optionally accept a level of resilience for the random TTG
    parser.add_argument('-r', '--rand-res', default=-1, type=int,
        help='For the random TTG, specify a level of resilience')

    # Optionally write out the forwarding table state
    parser.add_argument('-o', '--output',
        type=argparse.FileType('w'),
        help='Write the forwarding table state to a file (JSON)')

    # Optionally write out all of the wildfwdtables
    parser.add_argument('-w', '--writetable',
        type=argparse.FileType('w'),
        help='Write the forwarding table to a file (JSON) instead of stdout')

    # The input topology
    parser.add_argument('topo', type=argparse.FileType('r'),
        help='The YAML for the generated topology. MUST be syntactically \
        correct (e.g. the output from the topology generator (topo_gen.py)')

    # Parse the arguments
    args = parser.parse_args()
    topo = yaml.load(args.topo, Loader=yaml.CLoader)
    switches = topo['Switches']
    V, E = build_graph(switches)
    G = (V, E)
    iG = mygraph_to_igraph(V, E)

    # Some extra argument error checking
    if args.default_trees < 0:
        sys.stderr.write('The number of default trees must not be negative\n')
        sys.exit(1)
    if args.num_trees == 0 and args.default_trees == 0:
        sys.stderr.write('The number of trees cannot be 0\n')
        sys.exit(1)
    if args.model == Models.EDST and args.num_trees > 0 and \
            not args.maxl1 > 0 and \
            args.ttg_type in (TTGs.MLAYER, TTGs.ALAYER, TTGs.T):
        sys.stderr.write('Number of trees requires a maximum l1 width for the Mlayer, ALayer, and T TTGs.\n')
        sys.exit(1)
    if args.dfr and (args.default_trees != 0):
        sys.stderr.write('DFR does not support default trees\n')
        sys.exit(1)
    if args.dfr and not args.model == Models.EDST:
        sys.stderr.write('DFR current requires EDST\n')
        sys.exit(1)
    if args.dfr and args.ttg_type == TTGs.UNSET:
        sys.stderr.write('DFR requires a TTG to be specified\n')
        sys.exit(1)
    if args.ttg_type in (TTGs.RAND, TTGs.MAXDAG) and args.rand_res < 0:
        sys.stderr.write('TTG ' + TTGs.RAND + ' and ' + TTGs.MAXDAG + ' require rand-res to be specified.\n')
        sys.exit(1)
    if args.ttg_type in (TTGs.MLAYER, TTGs.ALAYER, TTGs.T) and args.l1width <= 0:
        sys.stderr.write('TTGs ' + TTGs.MLAYER + ' and ' + TTGs.ALAYER +
            ' and ' + TTGs.T + ' require a l1width greater than 0.\n')
        sys.exit(1)

    # Optionally create a global wildfwdtable
    firstglobalwrite = True

    # Save the global (all-dst) state for each switch.
    #TODO: adapt
    global_tcam_state = {}
    tothosts = reduce(lambda acc, v: v.numhosts + acc, V, 0)
    for v in V:
        sw_dst_bits = int(math.ceil(math.log(len(filter(
            lambda v: v.numhosts > 0, V)), 2)))
        hosts_dst_bits = int(math.ceil(math.log(tothosts, 2)))
        global_tcam_state[v.name] = {
            'sw_dst_bits': sw_dst_bits,
            'host_dst_bits': hosts_dst_bits,
            'port_bits': v.tot_ports,
            'sw_tcam': 0,
            'hosts_tcam': 0,
            'nopkthdr_sw_tcam': 0,
            'nopkthdr_hosts_tcam': 0,
            'label_bits': 0,
        }

    # DFR only builds as many forests as there are virtual queues (8 in the
    # case of ethernet).  This implies that the forests are independent of the
    # destinations and need to be build now in this case.  However, we would
    # expect better path diversity from using different forrests in the non-DFR
    # case, so we do not build the forests now unless we have DFR.
    if args.dfr:
        assert (args.model == Models.EDST)

        # Build the forest
        forest = edst_forest(G, iG, None)

        #DEBUG
        #print 'Num EDST:', len(forest)

        # Randomize the forest's order
        random.shuffle(forest)

        # Sort the trees in the forest by average path length.
        # I am doing this because earlier trees in the forest are used at lower
        # levels in the TTG than later trees, and thus are more likely to be
        # used.  In this case, we would like to use the more performant trees
        # first, i.e., those with a shorter average path length.
        #XXX: TODO: add disabling this sorting as a command line option! Science!
        #TODO: each call to Graph.average_path_length() may be expensive.
        forest.sort(lambda x, y: cmp(x.average_path_length(), y.average_path_length()))

        #DEBUG: Find the average path lengths of all of the trees in the forest
        #debug_avg_pathlen = [iT.average_path_length() for iT in forest]
        #print 'Average path lengths:', debug_avg_pathlen
        
        # Number the trees
        number_trees(forest)

        # Build a DFR tree transition graph (TTG)
        if args.ttg_type == TTGs.LINE:
            ttg = ttg_line(forest, args.num_trees)
        elif args.ttg_type == TTGs.NORES:
            ttg = ttg_nores(forest)
        elif args.ttg_type == TTGs.MLAYER:
            ttg = ttg_mred_layered_dag(forest, args.l1width, args.self_layer)
        elif args.ttg_type == TTGs.ALAYER:
            ttg = ttg_ared_layered_dag(forest, args.l1width, args.self_layer)
        elif args.ttg_type == TTGs.T:
            ttg = ttg_t_layered_dag(forest, args.l1width, args.self_layer)
        elif args.ttg_type == TTGs.RAND:
            ttg = ttg_rand_dag(forest, args.rand_res)
        elif args.ttg_type == TTGs.MAXDAG:
            ttg = ttg_max_dag(forest, args.rand_res)
        else:
            assert(0)

        # Assert some properties of the TTG
        assert (ttg.is_dag())
        assert (ttg.is_directed())

        #XXX: DEBUG
        #print ttg
        #sys.exit(1)
    else:
        forest = None
        ttg = None

    for dst in V:
        # Quit if there are no destinations
        if dst.numhosts == 0:
            continue

        #print 'dst:', dst

        # Init the fwd tables
        for v in V:
            #XXX: Reset fwdtable and wildfwdtable.  Hack to reclaim memory for multiple dsts
            #TODO: move this to where the table is written
            v.fwdtable = []
            v.nopkthdr_fwdtable = []

        # Build the init paths
        #TODO: Optionally add some shortest path trees for each destination
        
        # Build the forest of trees
        if args.dfr:
            assert (forest != None)
            assert (ttg != None)
        else:
            assert (ttg == None)
            assert(args.default_trees >= 0)

            dtrees = [build_default_tree(V, E, iG, dst) for i in range(args.default_trees)]

            quit_early = args.num_trees >= 0
            if args.model == Models.EDST:
                forest = edst_forest(G, iG, dst,
                    num_trees = args.num_trees, quit_early = quit_early)
                #print 'Num EDST:', len(forest)
            elif args.model == Models.ADST:
                forest = adst_forest(G, iG, dst,
                    num_trees = args.num_trees, quit_early = quit_early)

                if len(forest) < args.num_trees:
                    print '|forest|:', len(forest), 'args.num_trees:', args.num_trees
                #assert(len(forest) >= args.num_trees)

                #print 'Num ADST:', len(forest)

                #DEBUG: Find the average path lengths of all of the trees in the forest
                debug_avg_pathlen = [iT.average_path_length() for iT in forest]
                #print 'Average path lengths:', debug_avg_pathlen
            else:
                assert(0)

            # Label the trees as default or not and combine the default and
            # non-default trees
            for dtree in dtrees:
                dtree['default'] = True
            for tree in forest:
                tree['default'] = False
            forest = dtrees + forest

            # Randomize the forest's order
            #random.shuffle(forest)

            # Number the trees
            number_trees(forest)

        # Quit early and print the number of trees if requested
        if args.max_trees:
            print '%d trees' % len(forest)
            sys.exit(0)

        # Compute routes for each vertex for each tree in the forest.
        # Conveniently identical for edst and adst.
        fpaths = forest_paths(G, forest, dst)

        #DEBUG
        for v in V:
            for iT in forest:
                assert(iT in fpaths[v])

        #DEBUG
        #for v in V:
        #    print v, '-->', fpaths[v].values()

        # Build the forwarding tables
        if args.model == Models.EDST:
            #TODO: build the forwarding table
            edst_fwdtable(G, forest, fpaths, ttg, dst, args)
        elif args.model == Models.ADST:
            assert(ttg == None)
            adst_fwdtable(G, forest, fpaths, dst, args)
        else:
            assert(0)

        #DEBUG
        #for v in V:
        #    print 'v:', v
        #    print_fwdtable(v.fwdtable)

        # Update the global forwarding table state count
        for v in V:
            sw_tcam = len(filter(lambda x: x[1] != None, v.fwdtable))
            hosts_tcam = sw_tcam * dst.numhosts
            global_tcam_state[v.name]['sw_tcam'] += sw_tcam
            global_tcam_state[v.name]['hosts_tcam'] += hosts_tcam

            nopkthdr_sw_tcam = len(filter(lambda x: x[1] != None, v.nopkthdr_fwdtable))
            nopkthdr_hosts_tcam = sw_tcam * dst.numhosts
            global_tcam_state[v.name]['nopkthdr_sw_tcam'] += nopkthdr_sw_tcam
            global_tcam_state[v.name]['nopkthdr_hosts_tcam'] += nopkthdr_hosts_tcam

            # DFR requires no additional label bits
            label_bits = max(global_tcam_state[v.name]['label_bits'], len(forest)) \
                if not args.dfr else 0
            global_tcam_state[v.name]['label_bits'] = label_bits

        # Write out the forwarding table to args.writetable
        if args.writetable:
            # Bookeeping
            if firstglobalwrite:
                firstglobalwrite = False
                args.writetable.write('[\n')
            else:
                args.writetable.write(',\n')

            # Create a fwdtable that uses names instead of objects
            globalwritetable = {}
            for v in V: 
                globalwritetable[v.vnum] = []
                # (dst, curr_tree, up_tree, up_e) -> 
                #   (out_p, marked_failed_trees)
                for key, value in v.fwdtable:
                    dst, iT, aiT, e = key
                    port, mark_failed = value
                    assert(iT == None or iT['index'] > 0)
                    assert(aiT['index'] > 0)
                    iTi = 0 if iT == None else iT['index']
                    ge = [[dst.vnum, iTi, aiT['index'], e.enum],
                          [port, [_iT['index'] for _iT in mark_failed]]]
                    #print ge
                    globalwritetable[v.vnum].append(ge)

            for chunk in jsone.iterencode(globalwritetable):
                args.writetable.write(chunk)

    if args.output:
        for chunk in jsone.iterencode(global_tcam_state):
            args.output.write(chunk)
    #print 'global_tcam_state:', global_tcam_state

    # Finish writing the wildtable, if requested
    if args.writetable:
        args.writetable.write(']\n')

if __name__ == "__main__":
    main()
