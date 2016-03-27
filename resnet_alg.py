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
from priority_dict import *

#jsone = json.JSONEncoder(indent=2, separators=(',', ': '))
#jsone = json.JSONEncoder()
jsone = myjsone.myJSONEncoder(indent=2, maxindent=3, separators=(', ', ': '))

num_paths_per_v = 0

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
        # Fwd table is (revpath, link that must be up, links that must be down) -> path
        self.fwdtable = {}
        self.wildfwdtable = []
 
        # v -> portnums connected to v
        self.nbr_ports = {}

    def __repr__(self):
        return self.name
    def __len__(self):
        return len(self.__repr__())

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
    def __len__(self):
        return len(self.__repr__())

#class Path(object):
class Path:
    #dstPathIds = {}
    ##newid = itertools.count().next
    ##Path.newid()
    def __init__(self, v, path, failedE = set(), rPath = [], failedV = set(), fullPath = None):
        self.v = v
        if path is not None and len(path) > 0:
            self.path = tuple(path)
            #print 'path:', path, 'fullPath:', fullPath
            if fullPath:
                self.fullPath = tuple(fullPath)
                self.rv, self.rpath = reverse_path(v, self.fullPath)
            else:
                self.fullPath = self.path
                self.rv, self.rpath = reverse_path(v, path)
            self.dst = self.rv
            #if self.dst not in Path.dstPathIds:
            #    Path.dstPathIds[self.dst] = itertools.count().next
            #    Path.dstPathIds[self.dst]()
            #self.dstPid = Path.dstPathIds[self.dst]()
            #assert(self.dstPid > 0)
        else:
            self.path = None
            self.fullPath = None
            self.rv, self.rpath = None, None
            self.dst, self.dstPid = None, -1
        self.failedE = failedE
        self.failedV = failedV
        self.extraRPath = rPath
        self.newpath = None

        self.edges, self.vertices, self.arcs = set(), set(), set()
        currv = v
        self.vertices.add(currv)
        if self.fullPath is not None:
            for hop in self.fullPath:
                self.edges.add(currv.edges[hop])
                self.arcs.add((currv, currv.edges[hop]))
                currv = currv.ports[hop]
                self.vertices.add(currv)
        assert(self.edges.isdisjoint(self.failedE))
        #assert(self.vertices.isdisjoint(self.failedV))

    def __repr__(self):
        return str((self.v, self.path))

def reverse_path(src, path):
    revpath = []
    v = src
    if path is not None:
        for hop in path:
            e = v.edges[hop]
            nextv, revhop = e.get_other(v, hop)
            revpath.append(revhop)
            v = nextv
        revpath.reverse()
    return v, revpath

def arc_set(src, path):
    currv = src
    arcSet = set()
    for hop in path:
        arcSet.add((currv, currv.edges[hop]))
        currv = currv.ports[hop]
    return arcSet

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

def build_tree(V, E, iG, dst, failedE = set(), failedV = set(), fail = 'edges'):
    if fail == 'vertcies' and dst in failedV:
        return None

    #print 'dst:', dst
    #print 'V:', V
    #print 'failedV:', failedV

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

    #print 'subG:', [v['name'] for v in sub_iG.vs]

    # Get the parents in the BFS search
    try:
        dstid = sub_iG.vs.find(name=dst).index
    except ValueError:
        return None
        
    ret = sub_iG.bfs(dstid)
    visited, parents = ret[0], ret[2]
    #print 'dstid:', dstid
    ##print 'visited:', visited
    #print 'parents:', parents

    # Build a tree
    iT = igraph.Graph()
    iT.to_directed()

    # Add the vertices
    #vs = [sub_iG.vs[igid]['name'] for igid in visited]
    vs = sub_iG.vs
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
            if e not in failedE:
                edge_opts.append(e)
        e = random.choice(edge_opts)
        #assert(e.v1 == p or e.v2 == p)
        #assert(e.v1 == c or e.v2 == c)
        edge_map[(cid, pid)] = e
    iT.add_edges(edge_map.iterkeys())
    for iE in iT.es:
        iE['name'] = edge_map[iE.tuple]
    #print 'iT:', iT
    return iT

    print 'islandid:', [v.index for v in sub_iG.vs if v['name'].name == 'switch.island']
    print 'dstid:', dstid
    print ret
    vids = [v.index for v in sub_iG.vs]
    pc = [(parents[i], c) for i, c in enumerate(vids)]
    out = {}
    for vid in vids:
        #print 'vid:', vid, 'pathlen:', sub_iG.shortest_paths(vid, dstid)
        out[vid] = sub_iG.shortest_paths(vid, dstid)
    pathlens = [out[vid] for vid in ret[0]]
    print pathlens
    #pathlens = sub_iG.shortest_paths(vids, dstid)
    #print 'vs:', [v.index for v in sub_iG.vs]
    #print zip(vids, pathlens)
    #print pathlens

    parents = ret[2]
    pc = [(parents[i], c) for i, c in enumerate(vids)]
    print pc
    matchpathlens = [(out[p][0][0], out[c][0][0]) for p, c in pc]
    print matchpathlens
    for pl, cl in matchpathlens:
        if cl <= pl:
            print pl, cl, 'violates the parent child relationship in a BFS'
    sys.exit(1)

    return iT

def shortest_path(V, E, iG, src, dst, failedE = set(), extraRevPath = [], failedV = set(), fail = 'edges', dfr = False, arcSet = set()):
    if src == dst:
        return Path(src, None, failedE, extraRevPath, failedV)
    assert(dst.numhosts > 0)

    if iG == None:
        return Path(src, None, failedE, extraRevPath, failedV)

    if fail == 'vertices' and dst in failedV:
        return Path(src, None, failedE, extraRevPath, failedV)

    if dfr:
        assert(fail != 'vertices') # Not yet implemented

        # To directed because we need to ensure that we never use the
        # same arc (port) twice.
        assert(not iG.is_directed())  #XXX: should be old FCP specific stuff
        sub_iG = iG.copy()
        sub_iG.to_directed()

        # Find the eigids for either the used arcs or failed edges
        is_arc_removed = lambda ie: ie['name'] in failedE or (sub_iG.vs[ie.source]['name'], ie['name']) in arcSet
        #eigids = filter(is_arc_removed, sub_iG.es)
        eigids = [ie for ie in sub_iG.es if is_arc_removed(ie)]

        # Debug:
        #print 'failedE:', failedE
        #print 'used arcs:', arcSet
        #print 'removed eigids:'
        #for ie in eigids:
        #    print '   ', ie, ie.source, sub_iG.vs[ie.source]['name'], '-->', ie.target, sub_iG.vs[ie.target]['name']
        #print

        # Remove the arcs (eigids)
        sub_iG.delete_edges(eigids)
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

class PercentileHeap(object):
    def __init__(self, max_elem, percentile):
        self.heap = []
        self.max_elem = max_elem
        self.curr_elem = 0
        self.percentile = percentile
        self.max_size = int(math.ceil(max_elem * (100 - percentile) / 100.0))
        self.curr_size = 0

    def push(self, item):
        # Make sure we haven't exeeded the max elements
        self.curr_elem += 1
        if self.curr_elem > self.max_elem:
            raise ValueError('Too many elements!')
        
        # Add the element
        if self.curr_size < self.max_size:
            heapq.heappush(self.heap, item)
            self.curr_size += 1
        else:
            heapq.heappushpop(self.heap, item)

    def get_percentile(self):
        #try:
        #    assert(self.curr_elem == self.max_elem)
        #except:
        #    sys.stderr.write('%d != %d\n' % (self.curr_elem, self.max_elem))
        #    sys.stderr.writelines(sys.argv)
        #    raise
        return heapq.heappop(self.heap)

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

def update_deps(deps, path, edgeDeps, fail='edges'):
    currv = path.v
    for hop in path.path:
        e = currv.edges[hop]
        assert(e not in edgeDeps)
        if fail == 'edges':
            eset = frozenset((e,)) | edgeDeps
        if fail == 'vertices':
            nextv = currv.ports[hop]
            eset = set()
            for edge in nextv.edges.itervalues():
                eset.add(edge)
            eset = edgeDeps | eset
        if eset not in deps:
            deps[eset] = []
        deps[eset].append(path)
        currv = currv.ports[hop]

def combine_masks(mask1, mask2):
    new_mask = []
    for i in xrange(len(mask1)):
        if mask1[i] == '1' or mask2[i] == '1':
            if mask1[i] == '1' and mask2[i] == '1':
                new_mask.append('1')
            else:
                print 'Cannot combine masks!', mask1, mask2
                return None
        elif mask1[i] == '*' or mask2[i] == '*':
            new_mask.append('*')
        else:
            new_mask.append('0')
    return ''.join(new_mask)

def rpath_matches(rpath, match):
    for i in xrange(len(rpath)):
        if match[i] != '*' and rpath[i] != match[i]:
            return False
    return True

def fwd_entry_matches(rpath, mask, match_rpath, match_mask):
    if not rpath_matches(rpath, match_rpath):
        return False
    for i in xrange(len(mask)):
        if match_mask[i] != '*' and mask[i] != '*' and \
                mask[i] != match_mask[i]:
            return False
    return True

def find_nonmatching_entry(rpath, match, full_rpath):
    new_match = []
    for i in xrange(len(rpath)):
        if rpath[i] == match[i]:
            new_match.append(rpath[i])
        elif match[i] == '*':
            if rpath[i] == full_rpath[i]:
                new_match.append(rpath[i])
            else:
                new_match.append(full_rpath[i])
                return tuple(new_match) + match[i+1:]
        else:
            print 'RPaths are already non-matching'
            sys.exit(1)
    print 'No nonmatching rpath exists?! ERROR?!', rpath, match, full_rpath
    return None

def build_wild_table(v):
    ports = v.edges.keys()
    ports.sort()
    items = v.fwdtable.items()

    # Build the edge mask and find the longest rpath
    maxrpathlen = reduce(lambda x, y: max(x, len(y[0][0])), items, 0)
    for (rpath, uplink, localFailedE), path in items:
        expand_rpath = rpath + tuple(([-1] * (maxrpathlen + 1 - len(rpath))))
        edge_mask = ''
        for port in reversed(ports):
            if v.edges[port] == uplink:
                edge_mask += '1'
            elif v.edges[port] in localFailedE:
                edge_mask += '0'
            else:
                edge_mask += '*'
        v.wildfwdtable.append((expand_rpath, edge_mask, path))
    v.wildfwdtable = sort_wild_table(v.wildfwdtable)

def sort_wild_table(wildtable):
    # Find the number of each of the unique paths
    paths = {}
    numpaths = {}
    for rpath, edge_mask, path in wildtable:
        if path.path not in paths:
            paths[path.path] = []
            numpaths[path.path] = 0
        paths[path.path].append((rpath, edge_mask, path))
        num_wild = edge_mask.count('*')
        numpaths[path.path] += (2 ** num_wild)

    # Sort the items
    def sort_items(x, y):
        rpath1, edge_mask1, path1 = x
        rpath2, edge_mask2, path2 = y
        if path1.path == None and path2.path == None:
            return 0
        elif path1.path == None:
            return 1
        elif path2.path == None:
            return -1

        # Sort by the size of the exact match table, not the number of paths
        #pathdiff = cmp(len(paths[path1.path]), len(paths[path2.path]))
        pathdiff = cmp(numpaths[path1.path], numpaths[path2.path])
        if pathdiff == 0:
            edgediff = cmp(edge_mask1, edge_mask2)
            if edgediff == 0:
                return cmp(rpath1, rpath2)
            else:
                return edgediff
        else:
            return pathdiff
    wildtable.sort(sort_items)
    wildtable.reverse()
    return wildtable

def check_wildfwdtable(v):
    for rpath, mask, path in v.wildfwdtable:
        for o_rpath, o_mask, o_path in v.wildfwdtable:
            if fwd_entry_matches(rpath, mask, o_rpath, o_mask) and \
                    path.path != o_path.path:
                print 'The following entries match!'
                print rpath, mask, '->', path.path
                print o_rpath, o_mask, '->', o_path.path
                print 'path.failedE: %s, path.edges: %s' % \
                    (path.failedE, path.edges)
                print 'o_path.failedE: %s, o_path.edges: %s' % \
                    (o_path.failedE, o_path.edges)
                return False
    return True
def check_new_wildtable(table):
    for inbits, path in table:
        for o_inbits, o_path in table:
            if entry_matches(inbits, o_inbits) and \
                    path.path != o_path.path:
                return False
    return True

def entry_matches(inbits, match_inbits):
    raise DeprecationWarning('This function is ambiguous and is being fazed out.')
    #assert(0)
    assert(len(inbits) == len(match_inbits))
    for i in xrange(len(inbits)):
        if match_inbits[i] != '*' and inbits[i] != '*' and \
                inbits[i] != match_inbits[i]:
            return False
    return True

def partial_matches(inbits, match_inbits):
    assert(len(inbits) == len(match_inbits))
    for i in xrange(len(inbits)):
        if match_inbits[i] != '*' and inbits[i] != '*' and \
                inbits[i] != match_inbits[i]:
            return False
    return True

def complete_matches(inbits, match_inbits):
    assert(len(inbits) == len(match_inbits))
    for i in xrange(len(inbits)):
        if inbits == '*' and match_inbits[i] != '*':
            return False
        if match_inbits[i] != '*' and inbits[i] != '*' and \
                inbits[i] != match_inbits[i]:
            return False
    return True


def find_nonmatching_inbits(inbits, match, orig_inbits):
    new_match = []
    for i in xrange(len(inbits)):
        if inbits[i] == match[i]:
            new_match.append(inbits[i])
        elif inbits[i] == '*':
            new_match.append(match[i])
        elif match[i] == '*':
            if inbits[i] != orig_inbits[i]:
                new_match.append(orig_inbits[i])
                return tuple(new_match) + match[i+1:]
            else:
                new_match.append(match[i])
                #new_match.append(orig_inbits[i])
        else:
            print 'Inbits are already non-matching!'
            sys.exit(1)
    print 'No nonmatching inbits exists?! ERROR?!', inbits, match, orig_inbits
    return None

def wild_hamming_dist(inbits, match):
    dist = set()
    for i in xrange(len(inbits)):
        if match[i] != '*' and inbits[i] == '*':
            dist.add(i)
        elif match[i] != '*' and inbits[i] != match[i]:
            dist.add(i)
    return dist

def newer_pack_tcam(wildtable):
    if len(wildtable) == 0:
        return wildtable
        
    maxinbits = len(wildtable[0][0])
    assert(all(map(lambda x: len(x[0]) == maxinbits,
                   wildtable)))
    base_mask = ('*',) * maxinbits
    drop_path = Path(None, None, set(), ())

    # Build the init TCAM with only a drop rule
    tcam = [(base_mask, drop_path)]

    # Define a helper function for building the mask
    def pick_next_entries(curr_inbits, prev_inbits):
        #print 'curr_inbits:', curr_inbits
        #print 'prev_inbits:', prev_inbits
        entries = set([curr_inbits[0]])
        for inbits in curr_inbits:
            #XXX
            #print 'inbits:', inbits
            #print 'New_entries:'
            #for tmp in entries:
            #    print '\t', tmp

            # Compute the hamming distance from the entries
            hamming_dist = {}
            for new_entry in entries:
                dist = wild_hamming_dist(inbits, new_entry)
                if dist != None:
                    hamming_dist[new_entry] = dist

            # We already have a matching entry, so we are done
            if set() in hamming_dist.values():
                #print 'Found \'set()\' in hamming_dist, quitting'
                continue

            # Try to find a new entry based on the hamming distances
            sorted_hamming_dist = hamming_dist.items()
            sorted_hamming_dist.sort(lambda x, y: cmp(len(x[1]), len(y[1])))

            #XXX: Try out a new sorting algorithm
            sorted_hamming_dist = map(lambda x: (x[0], tuple(x[1])), sorted_hamming_dist)
            len_path = len(filter(lambda x: type(x) == type(1), inbits))
            #sorted_hamming_dist.sort(lambda x, y: cmp(len(filter(lambda a: a >= len_path, x[1])), len(filter(lambda b: b >= len_path, y[1]))))

            def sort_hamming(x, y):
                pass

            #print 'Hamming dist:', sorted_hamming_dist
            #for new_entry, dist in sorted_hamming_dist:
            #    print '\t', new_entry, dist
            for new_entry, dist in sorted_hamming_dist:
                next_entry = list(new_entry)
                for bit_index in dist:
                    next_entry[bit_index] = '*'
                next_entry = tuple(next_entry)
                #print 'next_entry:', next_entry
                matches = map(lambda o_inbits: partial_matches(o_inbits, next_entry),
                    prev_inbits)
                #print 'matches:', matches
                if not any(matches):
                    #print 'No matches, changing entry.'
                    entries.remove(new_entry)
                    entries.add(next_entry)
                    break
            # We were unable to modify any of the new entries.  Add inbits
            # because it will match itself.
            else:
                #print 'Unable to modify new entries.'
                entries.add(inbits)

            #XXX
            #print 'Changed New_entries:'
            #for tmp in entries:
            #    print '\t', tmp

        return list(entries)

    curr_inbits, curr_path = [], None
    prev_inbits = []
    for inbits, path in wildtable:

        # We have already installed the drop rule
        if path.path == None:
            continue

        # Commit the current path if the new path differs
        if curr_path != None and curr_path.path != path.path:
            new_entries = pick_next_entries(curr_inbits, prev_inbits)
            for entry in new_entries:
                tcam.append((entry, curr_path))
                #print 'Adding to the packed table: %s -> %s' % (entry, curr_path)
            prev_inbits.extend(curr_inbits)

            #XXX: Sanity check
            for tmp in curr_inbits:
                matches = map(lambda x: entry_matches(tmp, x), new_entries)
                if not any(matches):
                    print 'inbits: %s do not match any entries!' % str(tmp)
                    for x in new_entries:
                        print x
                    sys.exit(1)

            curr_inbits, curr_path = [], None

        if curr_path == None:
            curr_path = path
        curr_inbits.append(inbits)

    # Finish up adding the last TCAM entries
    new_entries = pick_next_entries(curr_inbits, prev_inbits)
    for entry in new_entries:
        tcam.append((entry, curr_path))
        #print 'Adding to the packed table: %s -> %s' % (entry, curr_path)

    tcam.reverse()

    #print 'WildTable:'
    #for inbits, path in wildtable:
    #    print'\t%s -> %s' % (inbits, str(path.path))
    #print 'TCAM:'
    #for inbits, path in tcam:
    #    print'\t%s -> %s' % (inbits, str(path.path))
    #sys.exit(1)

    return tcam

def newer_tcam_entry_lens(v):
    entry_lens = [0] * (len(v.newer_tcam) - 1)
    for inbits, path in v.new_wildtable:
        # Get the rplen of the inbits
        try:
            rplen = inbits.index(-1)
        except ValueError:
            rplen = v.prefixlen

        for tcam_i, (tcam_mask, tcam_path) in enumerate(v.newer_tcam):
            if entry_matches(inbits, tcam_mask):
                if path.path == tcam_path.path:
                    if tcam_path.path != None:
                        new_rplen = max(entry_lens[tcam_i], rplen)
                        entry_lens[tcam_i] = new_rplen
                    break
                else:
                    print 'ERROR! TCAM is not correct!'
                    print '(%s, %s) matched (%s, %s)' % (inbits, path.path, tcam_mask, tcam_path.path)
                    sys.exit(1)
    return entry_lens

def newer_check_tcam(v):
    for inbits, path in v.new_wildtable:
        matched = False
        for tcam_mask, tcam_path in v.newer_tcam:
            if complete_matches(inbits, tcam_mask):
                if path.path == tcam_path.path:
                    matched = True
                    break
                else:
                    print 'ERROR! TCAM is not correct!'
                    print '(%s, %s) matched (%s, %s)' % (inbits, path.path, tcam_mask, tcam_path.path)
                    return False
            if partial_matches(inbits, tcam_mask):
                if path.path != tcam_path.path:
                    print 'ERROR! TCAM is not correct!'
                    print '(%s, %s) partial matched (%s, %s)' % (inbits, path.path, tcam_mask, tcam_path.path)
                    return False
        if not matched:
            print 'ERROR! TCAM is not correct!'
            print '(%s, %s) do not have a match' % (inbits, path.path)
            return False
    return True

def new_pack_tcam(wildtable, usebasemask=True):
    # Find the number of each of the unique paths
    paths = {}
    numpaths = {}
    for inbits, path in wildtable:
        if path.path not in paths:
            paths[path.path] = []
            numpaths[path.path] = 0
        paths[path.path].append((inbits, path))
        num_wild = inbits.count('*')
        #XXX: is it correct to sort by wild bits, because at these point they
        # only specify which ports should be down
        numpaths[path.path] += (2 ** num_wild)

    # Sort the items
    def sort_items(x, y):
        in1, path1 = x
        in2, path2 = y
        if path1.path == None and path2.path == None:
            return 0
        elif path1.path == None:
            return 1
        elif path2.path == None:
            return -1

        # Sort by the size of the exact match table, not the number of paths
        #pathdiff = cmp(len(paths[path1.path]), len(paths[path2.path]))
        pathdiff = cmp(numpaths[path1.path], numpaths[path2.path])
        if pathdiff == 0:
            return cmp(in1, in2)
        else:
            return pathdiff
    #wildtable.sort(sort_items)
    #wildtable.reverse()

    maxinbits = len(wildtable[0][0]) if len(wildtable) > 0 else 0
    assert(all(map(lambda x: len(x[0]) == maxinbits,
                   wildtable)))
    base_mask = ('*',) * maxinbits
    drop_path = Path(None, None, set(), ())

    # Build the init TCAM with only a drop rule
    tcam = [(base_mask, drop_path)]
    entry_to_inbits = {}

    # Define a helper for building a new entry
    def pick_new_entry(inbits):
        if usebasemask:
            entry = list(base_mask)
            #XXX: Hack because I always want the out edge to have a one
            # in the table
            one_index = 0
            for bit in reversed(inbits):
                one_index -= 1
                if bit == '1':
                    entry[one_index] = '1'
                    break
        else:
            len_path = len(filter(lambda x: type(x) == type(1), inbits))
            entry = (['*'] * len_path) + list(inbits[len_path:])
        entry = tuple(entry)
        return entry

    # Define a helper function for building the mask
    def pick_next_curr(curr_entries, inbits, path, i):
        new_entries = curr_entries
        retry_flag = True
        while retry_flag:
            for o_inbits, o_path in wildtable[i::-1]:
            #for o_inbits, o_path in wildtable[0:i+1]:
                break_flag = False
                match_flag = False if path.path == o_path.path else True
                for j in xrange(len(new_entries)):
                    new_inbits = new_entries[j]
                    if entry_matches(o_inbits, new_inbits):
                        if path.path == o_path.path:
                            #print 'Matching entry with same path', o_inbits, new_inbits, path
                            match_flag = True
                        else:
                            # Matching entry but different paths. Needs fixing
                            #print 'Matching entry with diff path!', o_inbits, o_path.path, new_inbits, path.path
                            orig_inbits = entry_to_inbits[new_inbits]
                            if new_inbits == orig_inbits:
                                print 'ERROR! At original inbits but still matching diff path!'
                                sys.exit(1)
                            next_inbits = find_nonmatching_inbits(o_inbits,
                                new_inbits, orig_inbits)
                            if next_inbits == None:
                                print 'ERROR! no next_inbits!'
                                sys.exit(1)
                            else:
                                new_inbits = next_inbits
                            new_entries[j] = new_inbits
                            entry_to_inbits[new_inbits] = orig_inbits
                            #print 'orig_inbits: %s' % str(orig_inbits)
                            #print 'new inbits: %s' % str(new_inbits)
                            break_flag = True
                            break
                if break_flag:
                    break
                if not match_flag:
                    #print 'No matching entry for (%s -> %s) found! Adding a new base entry and restarting' % (o_inbits, o_path.path)
                    new_entry = pick_new_entry(o_inbits)
                    new_entries.append(new_entry)
                    entry_to_inbits[new_entry] = o_inbits
                    break
            else:
                #print 'Finished loop without breaking. Quitting'
                retry_flag = False
        return new_entries

    curr_entries, curr_path = [], None
    for i, (inbits, path) in enumerate(wildtable):

        # We have already installed the drop rule
        if path.path == None:
            continue

        # Commit the current path if the new path differs
        if curr_path != None and curr_path.path != path.path:
            for curr_inbits in curr_entries:
                tcam.append((curr_inbits, curr_path))
                #print 'Adding to the packed table: %s -> %s' % (curr_inbits, curr_path)
            curr_entries, curr_path = [], None
            entry_to_inbits = {}

        if curr_path == None:
            entry = pick_new_entry(inbits)
            curr_entries.append(entry)
            curr_path = path
            entry_to_inbits[entry] = inbits
        curr_entries = pick_next_curr(curr_entries, inbits, curr_path, i)
    # Finish up adding the last TCAM entries
    if curr_path != tcam[-1][1]:
        for curr_inbits in curr_entries:
            tcam.append((curr_inbits, curr_path))
            #print 'Adding to the packed table: %s -> %s' % (curr_inbits, curr_path)

    tcam.reverse()

    #print 'WildTable:'
    #for inbits, path in wildtable:
    #    print'\t%s -> %s' % (inbits, str(path.path))
    #print 'TCAM:'
    #for inbits, path in tcam:
    #    print'\t%s -> %s' % (inbits, str(path.path))
    #sys.exit(1)

    return tcam

def new_tcam_entry_lens(v):
    entry_lens = [0] * (len(v.new_tcam) - 1)
    for inbits, path in v.new_wildtable:
        # Get the rplen of the inbits
        try:
            rplen = inbits.index(-1)
        except ValueError:
            rplen = v.prefixlen

        for tcam_i, (tcam_mask, tcam_path) in enumerate(v.new_tcam):
            if entry_matches(inbits, tcam_mask):
                if path.path == tcam_path.path:
                    if tcam_path.path != None:
                        new_rplen = max(entry_lens[tcam_i], rplen)
                        entry_lens[tcam_i] = new_rplen
                    break
                else:
                    print 'ERROR! TCAM is not correct!'
                    print '(%s, %s) matched (%s, %s)' % (inbits, path.path, tcam_mask, tcam_path.path)
                    sys.exit(1)
    return entry_lens

def new_check_tcam(v):
    for inbits, path in v.new_wildtable:
        matched = False
        for tcam_mask, tcam_path in v.new_tcam:
            if complete_matches(inbits, tcam_mask):
                if path.path == tcam_path.path:
                    matched = True
                    break
                else:
                    print 'ERROR! TCAM is not correct!'
                    print '(%s, %s) matched (%s, %s)' % (inbits, path.path, tcam_mask, tcam_path.path)
                    return False
            if partial_matches(inbits, tcam_mask):
                if path.path != tcam_path.path:
                    print 'ERROR! TCAM is not correct!'
                    print '(%s, %s) matched (%s, %s)' % (inbits, path.path, tcam_mask, tcam_path.path)
                    return False
        if not matched:
            print 'ERROR! TCAM is not correct!'
            print '(%s, %s) do not have a match!' % (inbits, path.path)
            return False
    return True

def new_check_table(wildtable, tcam):
    for inbits, path in wildtable:
        for tcam_mask, tcam_path in tcam:
            if entry_matches(inbits, tcam_mask):
                if path == tcam_path:
                    break
                else:
                    print 'ERROR! TCAM is not correct!'
                    print '(%s, %s) matched (%s, %s)' % (inbits, path, tcam_mask, tcam_path)
                    return False
        else:
            print 'ERROR! TCAM is incomplete!'
            print '(%s, %s) matched nothing' % (inbits, path)
            return False
    return True


def pack_tcam(v):
    ports = v.edges.keys()
    ports.sort()
    items = v.fwdtable.items()
    maxrpathlen = reduce(lambda x, y: max(x, len(y[0][0])), items, 0)
    drop_rpath = tuple((['*'] * (maxrpathlen + 1)))
    drop_mask = '*' * len(ports)
    drop_path = Path(v, None, set(), ())
    tcam = [(drop_rpath, drop_mask, drop_path)]
    base_rpath = tuple(['*'] * maxrpathlen) + (-1,)

    # Define a helper function for building the mask
    def pick_next_curr(curr_entries, rpath, path, i):
        new_entries = curr_entries
        #entry_to_rpath = {entry: rpath for entry in new_entries}
        entry_to_rpath = dict([(entry, rpath) for entry in new_entries])
        #entry_to_mask = {entry: entry[1] for entry in new_entries}
        entry_to_mask = dict([(entry, entry[1]) for entry in new_entries])
        flag = True
        while flag:
            #XXX
            #for new_rpath, new_mask in new_entries:
            #    print 'Starting pick_next: %s %s -> %s' % (new_rpath, new_mask, path)
            for o_rpath, o_mask, o_path in v.wildfwdtable[i::-1]:   
            #for o_rpath, o_mask, o_path in v.wildfwdtable[0:i+1]:   
                break_flag = False
                match_flag = False if path.path == o_path.path else True
                for j in xrange(len(new_entries)):
                    new_rpath, new_mask = new_entries[j]

                    # Combine masks if the paths are the same and the rpath matches
                    #if path.path == o_path.path and \
                    #        rpath_matches(o_rpath, new_rpath):
                    #    tmp_rpath = entry_to_rpath[(new_rpath, new_mask)]
                    #    tmp_mask = entry_to_mask[(new_rpath, new_mask)]
                    #    new_mask = combine_masks(new_mask, o_mask)
                    #    new_entries[j] = (new_rpath, new_mask)
                    #    entry_to_rpath[(new_rpath, new_mask)] = tmp_rpath
                    #    entry_to_mask[(new_rpath, new_mask)] = tmp_mask

                    if fwd_entry_matches(o_rpath, o_mask, new_rpath, new_mask):
                        if path.path == o_path.path:
                            #print 'Matching entry with same path', o_rpath, new_rpath, path
                            match_flag = True
                        else:
                            #print 'Matching entry with diff path!', o_rpath, new_rpath
                            tmp_rpath = entry_to_rpath[(new_rpath, new_mask)]
                            tmp_mask = entry_to_mask[(new_rpath, new_mask)]
                            next_rpath = find_nonmatching_entry(o_rpath, 
                                new_rpath, tmp_rpath)
                            if next_rpath == None:
                                print o_rpath, o_mask, o_path.path, new_rpath, new_mask, path.path
                                #XXX: Hack for failing vertices.  There is still
                                # probably something else wrong with how the
                                # edge masks are set for failed vertices
                                if o_rpath == tmp_rpath:
                                    fixed_mask = []
                                    for fix_i in xrange(len(tmp_mask)):
                                        if o_mask[fix_i] == '1':
                                            fixed_mask.append('0')
                                        else:
                                            fixed_mask.append(tmp_mask[fix_i])
                                    tmp_mask = ''.join(fixed_mask)

                                #print 'Resetting mask from %s to %s' % (new_mask, tmp_mask)
                                new_mask = tmp_mask
                            else:
                                new_rpath = next_rpath
                            new_entries[j] = (new_rpath, new_mask)
                            entry_to_rpath[(new_rpath, new_mask)] = tmp_rpath
                            entry_to_mask[(new_rpath, new_mask)] = tmp_mask
                            #print 'new_rpath: %s. Breaking...' % str(new_rpath)
                            break_flag = True
                            break
                    else:
                        if path.path == o_path.path:
                            #print 'Non-Matching entry but same path!', o_rpath, new_rpath, path
                            pass
                if break_flag:
                    break
                if not match_flag:
                    #print 'No matching entry found! Adding a new base entry and restarting'
                    new_entries.append((base_rpath, o_mask))
                    entry_to_rpath[(base_rpath, o_mask)] = o_rpath
                    entry_to_mask[(base_rpath, o_mask)] = o_mask
                    #XXX:
                    #print 'No match for %s %s -> %s' % (o_rpath, o_mask, o_path.path)
                    #for a, b in new_entries:
                    #    print a, b
                    break
            else:
                #print 'Finished loop without breaking. Quitting'
                flag = False
        return new_entries

    curr_entries, curr_path = [], None
    for i, (rpath, edge_mask, path) in enumerate(v.wildfwdtable):

        # We have already installed the drop rule
        if path.path == None:
            continue

        # Commit the current path if the new path differs
        if curr_path != None and curr_path.path != path.path:
            for curr_rpath, curr_mask in curr_entries:
                tcam.append((curr_rpath, curr_mask, curr_path))
                #print 'Adding to the packed table: %s %s -> %s' % (curr_rpath, curr_mask, curr_path)
            curr_entries, curr_path = [], None

        if curr_path == None:
            curr_entries.append((base_rpath, edge_mask))
            curr_path = path
        curr_entries = pick_next_curr(curr_entries, rpath, curr_path, i)
    if curr_path != tcam[-1][2]:
        for curr_rpath, curr_mask in curr_entries:
            tcam.append((curr_rpath, curr_mask, curr_path))

    tcam.reverse()
    v.tcam = tcam
    return tcam

def check_tcam(v):
    for rpath, edge_mask, path in v.wildfwdtable:
        for tcam_rp, tcam_mask, tcam_path in v.tcam:
            if fwd_entry_matches(rpath, edge_mask, tcam_rp, tcam_mask):
                if path.path == tcam_path.path:
                    break
                else:
                    print 'ERROR! TCAM is not correct!'
                    print '(%s, %s, %s) matched (%s, %s, %s)' % (rpath, edge_mask, path.path, tcam_rp, tcam_mask, tcam_path.path)
                    return False
    return True

class LPM_Node(object):
    def __init__(self, prefix):
        self.prefix = prefix
        self.nexthops = set()
        self.parent = None
        self.children = set()
    def __repr__(self):
        #return str((self.prefix, self.nexthops, map(lambda x: x.prefix, self.children)))
        return str(self.prefix)

def pack_lpm(v, vpfirst = True):
    # Pass Zero: Create the nodes
    nodes = {}
    def get_node(prefix):
        if prefix in nodes:
            return nodes[prefix]
        else:
            node = LPM_Node(prefix)
            nodes[prefix] = node
            return node
    root = None
    for rpath, em, path in v.wildfwdtable:
        assert(all(map(lambda hop: hop < 255, rpath)))
        mask = ['*'] * (len(rpath) * 8)
        if root == None:
            root = get_node(tuple(mask)) 
        parent = root
        for i, rhop in enumerate(rpath):
            if rhop == -1:
                rhop = 255
            bits = '{0:08b}'.format(rhop)
            for j, bit in enumerate(bits):
                mask_index = (i * 8) + j
                mask[mask_index] = bit
                child = get_node(tuple(mask))
                child.parent = parent
                parent.children.add(child)
                assert(len(parent.children) <= 2)
                if i == (len(rpath) - 1) and j == 7:
                    child.nexthops.add(path.path)
                    #print 'child: %s, parent: %s, children: %s, nexthops: %s' % (child, child.parent, child.children, child.nexthops)
                parent = child

    # Define a function for inheriting nexthops
    def inherited(node):
        if len(node.parent.nexthops) > 0:
            return node.parent.nexthops
        else:
            return inherited(node.parent)

    # Pass One.1: expand the tree
    #XXX: Try adding a default route
    root.nexthops.add((-1,))
    nodeq = deque([root])
    while len(nodeq) > 0:
        node = nodeq.popleft()
        if len(node.children) == 1:
            star_idx = node.prefix.index('*')
            new_mask = list(node.prefix)
            child = node.children.__iter__().next()
            child_bit = child.prefix[star_idx]
            new_mask[star_idx] = '0' if child_bit == '1' else '1'
            new_child = get_node(tuple(new_mask))
            new_child.parent = node
            node.children.add(new_child)
        if len(node.nexthops) == 0:
            node.nexthops = set(inherited(node))
        nodeq.extend(node.children)

    # Pass One.2: Build the tree
    tree = [root]
    nextlevel = root.children
    while len(nextlevel) > 0:
        tree.extend(nextlevel)
        new_nextlevel = []
        for node in nextlevel:
            new_nextlevel.extend(node.children)
        nextlevel = new_nextlevel

    #XXX: See what happens if virtual ports are used first
    # Pass One.3: Assign virtual port numbers to the 
    if vpfirst:
        vpnum = 0
        nexthops_to_vpnum = {}
        #XXX: for an invalid default route
        nexthops_to_vpnum[frozenset(root.nexthops)] = -1
        print 'vports:'
        for node in tree:
            if len(node.nexthops) > 0:
                #print node.prefix, node.nexthops
                fset = frozenset(node.nexthops)
                if fset not in nexthops_to_vpnum:
                    print 'fset: %s -> %d' % (str(fset), vpnum)
                    nexthops_to_vpnum[fset] = vpnum
                    vpnum += 1
                node.nexthops = set((nexthops_to_vpnum[fset],))
                #print 'New nexthops:', node.prefix, node.nexthops

    # Pass Two: percolate up nexthops
    for node in reversed(tree):
        assert(len(node.children) <= 2)
        if len(node.children) > 0:
            #XXX: For the binary version
            assert(len(node.children) == 2)
            child_i = node.children.__iter__()
            nhs1, nhs2 = child_i.next().nexthops, child_i.next().nexthops
            intersection = nhs1 & nhs2
            if len(intersection) > 0:
                node.nexthops = intersection
            else:
                node.nexthops = nhs1 | nhs2

            #nexthops = node.children.__iter__().next().nexthops
            #intersection = reduce(lambda x, y: x & y.nexthops,
            #    node.children, nexthops)
            #if len(intersection) > 0:
            #    node.nexthops = intersection
            #else:
            #    union = reduce(lambda x, y: x | y.nexthops,
            #        node.children, nexthops)
            #    node.nexthops = union

    # Pass Three:
    for node in tree:
        if node != root:
            inhrt = inherited(node)
            assert(len(inhrt) == 1)
            if len(node.children) > 0:
                if inhrt <= node.nexthops:
                    node.nexthops = frozenset()
                else:
                    nhop = node.nexthops.pop()
                    node.nexthops = frozenset((nhop,))
            else:
                if inhrt == node.nexthops:
                    node.nexthops = frozenset()
                else:
                    node.nexthops = frozenset(node.nexthops)
        else:
            nhop = node.nexthops.pop()
            node.nexthops = frozenset((nhop,))
        if len(node.nexthops) > 0:
            #print 'node: %s, nexthops: %s' % (node, node.nexthops)
            pass
    nentries = 0
    for node in tree:
        if len(node.nexthops) > 0:
            nentries += 1
    #print 'nentries: %d' % nentries
    #print ''

    # Build the lpm table and the new wildfwdtable
    v.lpm = []
    for node in reversed(tree):
        if len(node.nexthops) > 0:
            assert(len(node.nexthops) == 1)
            next_lpm_i = len(v.lpm)
            v.lpm.append((node.prefix, (list(node.nexthops)[0], next_lpm_i)))
    print 'lpm:'
    for entry in v.lpm:
        print '\t%s' % str(entry)
        pass

    #XXX
    #print_wildfwdtable(v)

    v.lpm_wildtable = []
    for rpath, em, path in v.wildfwdtable:
        fix_rpath = map(lambda x: x if x >= 0 else 255, rpath)
        bit_rpath = tuple(reduce(lambda x, y: x + y, map(lambda i: '{0:08b}'.format(i), fix_rpath)))
        for prefix, output in v.lpm:
            if rpath_matches(bit_rpath, prefix):
                v.lpm_wildtable.append((output, em, path))
                break
        else:
            print 'ERROR! No match for rpath %s' % rpath
            sys.exit(1)
    v.lpm_wildtable = sort_wild_table(v.lpm_wildtable)
    v.new_lpm_wildtable = map(lambda x: (x[0] + tuple(x[1]), x[2]), v.lpm_wildtable)
    print_new_table(v, v.new_lpm_wildtable)
    if not check_new_wildtable(v.new_lpm_wildtable):
        print 'ERROR! Invalid new_lpm_wildtable!'
        sys.exit(1)
    v.new_lpm_tcam = new_pack_tcam(v.new_lpm_wildtable)

#
# Potential optimizations:
#   1) in hop-by-hop share matches across dsts
#   2) bits in labels can be reused if packets with the tag will never reach
#      both switches
#
def pack_exact_match(V, label_bits):

    #XXX: In order for rules to be compressed, both the output path AND the
    # packet modification operation must be the same!  I believe this
    # fundamentally prevents this from being possible!

    # First, we must sort the fwdtable according to number of each of the
    # unique paths at each switch
    for v in V:
        numpaths = {}
        for (pid, upe, downE), path in v.fwdtable.iteritems():
            if path.path is not None:
                if path.path not in numpaths:
                    numpaths[path.path] = 0
                numpaths[path.path] += 1

        # Function for sorting the items
        def sort_items(x, y):
            path1 = x[-1]
            path2 = y[-1]
            if path1.path == None and path2.path == None:
                return 0
            elif path1.path == None:
                return 1
            elif path2.path == None:
                return -1
            pathdiff = cmp(numpaths[path1.path], numpaths[path2.path])
            if pathdiff == 0:
                return cmp(x[:-1], y[:-1])
            else:
                return pathdiff

        v.sortfwdtable = [(pid, 0, upe, downE, path) for \
            (pid, upe, downE), path in v.fwdtable.iteritems()]
        v.sortfwdtable.sort(sort_items)
        v.sortfwdtable.reverse()

    # Print out the table to verify the sorted order
    for v in V:
        print '%s:' % str(v)
        for pid, etag, upe, downE, path in v.sortfwdtable:
            print '\t%d\t%d\t%s\t%s\t--> %s' % \
                (pid, etag, upe, str(downE), str(path.path))

    # Check the number of ports on the switch in the topology:
    for v in V:
        print '%s number of ports: %d' % (v, v.tot_ports)

    # Initialize the variables needed for compression
    Vlist = list(V)
    etag_bits = 0
    for v in Vlist:
        v.num_etag = 0
        v.fwdt_i = 0

    #
    # Define some helper functions for finding out the size of a switch's tables
    # as well as sorting
    #

    # Find the number of bits to implement a given number of etags
    def num_etag_to_bits(num_etag):
        # We can get one tag for free because it is the lowest priority rule,
        # and the tags do not affect higher-priority non-compresed rules.
        # Also, (1).bit_length() gets the number of bits need given an integer
        assert (numetag >= 0)
        if num_etag == 0:
            return 0
        return (etag - 1).bit_length()

    def tcam_width(v):
        #TODO: If we assume a programmable parser, then shouldn't each switch
        # be able to individually pull the compression bits specific to itself.
        # If we assume that this is possible, then the tcam width is not the
        # total number of extra bits in the header, but only the bits specific to
        # the switch.  However, if this is used then, regardless of the
        # destination, the bits in the tag must represent rules at the same
        # switches.
        return label_bits + etag_bits + v.tot_ports

    def tcam_height(v):
        # TODO: change to include speculative
        return len(v.tcam) + len(v.sortfwdtable) - v.fwdt_i

    def tcam_bits(v):
        return tcam_width(v) * tcam_height(v)

    def sort_tables_by_size(x, y):
        # cmp (y, x) to sort from high to low
        return cmp(tcam_bits(y), tcam_bits(x))
        
    # Forwarding table keys must be (unique id, first e, failed e) tuples.
    # This fact allows us to compress the first entry for free

    # Termination conditions for compression:
    #   1) there are no more rules in the switch to be compressed
    #   2) 2nd to large table is now larger than the compressed table before
    #    compression AND that table cannot be compressed for free to smaller
    #    than its original size
    #   3) the switch table is empty
    Vlist.sort(sort_tables_by_size)
    highwater = tcam_bits(Vlist[0])
    print 'highwater: %d' % highwater
    while True:
        Vlist.sort(sort_tables_by_size)
        
        # XXX: DEBUG
        for v in Vlist:
            print '%s: %d bits' % (v, tcam_bits(v))

        first = Vlist[0]
        first_osize = tcam_bits(first)
        second = Vlist[1] if len(Vlist) > 1 else None
        second_osize = tcam_bits(second) if second is not None else 0

        # Find the number of rules to compress
        new_fwdt_i = first.fwdt_i
        while new_fwdt_i < len(first.sortfwdtable) and \
              first.sortfwdtable[first.fwdt_i][-1].path == \
              first.sortfwdtable[new_fwdt_i][-1].path:
            new_fwdt_i += 1

        # If there is nothing to compress, quit:
        assert (new_fwdt_i >= first.fwdt_i)
        if (new_fwdt_i - first.fwdt_i) <= 1:
            break

        break

    # Cleanup
    #for v in V:
    #    v.sortfwdtable = []

    sys.exit(1)

def print_wildfwdtable(v):
    print '%s:' % v
    for rpath, edge_mask, path in v.wildfwdtable:
        print '\t%s,\t%s -> %s' % (rpath, edge_mask, str(path.path))
def print_tcam(v):
    print '%s:' % v
    for rpath, edge_mask, path in v.tcam:
        print '\t%s,\t%s -> %s' % (rpath, edge_mask, str(path.path))
def count_total_entries(v):
    cnt = 0
    for rpath, edge_mask, path in v.wildfwdtable:
        num_wild = edge_mask.count('*')
        cnt += (2 ** num_wild)
    return cnt
def print_new_table(v, table):
    print '%s:' % v
    for inbits, path in table:
        try:
            print '    ' + ''.join(inbits), '->', path
        except:
            print '   ', inbits, '->', path
        #len_path = len(filter(lambda x: type(x) == type(1), inbits))
        #print '\t%s,\t%s -> %s' % (str(inbits[0:len_path]), ''.join(inbits[len_path:]), str(path.path))
        #print '\t%s -> %s' % (str(inbits), str(path.path))

def bytes_bw_table(table, tcam, prefixlen):

    def len_table_entry(bits):
        abit_len = len(bits)
        assert(prefixlen % 8 == 0)
        for i in xrange(0, prefixlen, 8):
            if all(map(lambda x: x == '1', bits[i:i+8])):
                assert(all(map(lambda x: x == '1', bits[i:prefixlen])))
                abit_len = (i+8) + len(bits[prefixlen:])
                break
        return abit_len

    matches = {}
    for tcam_mask, tcam_path in tcam:
        if tcam_path is not None:
            matches[tuple(tcam_mask)] = []
    for inbits, path in table:
        if path is None:
            continue
        for tcam_mask, tcam_path in tcam:
            tcam_mask = tuple(tcam_mask)
            print inbits, tcam_mask
            if entry_matches(inbits, tcam_mask):
                assert(path == tcam_path)
                matches[tcam_mask].append(inbits)
                # Only the first match matters
                break
    if not all(map(lambda x: len(x) > 0, matches.itervalues())):
        #print 'There are %d unused TCAM entries' % \
        #    len(filter(lambda x: len(x) == 0, matches.itervalues()))
        for tcam_mask in matches.keys():
            if len(matches[tcam_mask]) == 0:
                del matches[tcam_mask]

    tcam_lens = dict([(tcam_mask, \
                        max(map(lambda x: len_table_entry(x), mask_matches))) \
                    for tcam_mask, mask_matches in matches.iteritems()])
    return sum(map(lambda x: int(math.ceil(x / 8.0)), tcam_lens.values()))
    
def ethfcp_fwdtable_path(dst, src, eid, fwd_trees):#, eid_to_failed):
    return True
    return False

def plinko_fwdtable_path(dst, src, failedE, extra_rp = ()):
    if src == dst:
        return extra_rp

    #localFailedE = failedE & src.edgeSet
    #print 'curr: (%s, %s, %s)' % (src, extra_rp, failedE)
    paths_for_rp = src.rp_fwdtable[extra_rp]
    for e_e, e_fe in paths_for_rp:
        #print 'entry: (%s, %s, %s)' % (e_rp, e_e, e_fe)
        if e_e not in failedE and e_fe <= failedE:
            path = paths_for_rp[e_e, e_fe]
            if path.path == None:
                return extra_rp
            currv, revpath = revpath_at_fail(path, failedE)
            return plinko_fwdtable_path(dst, currv, failedE, tuple(revpath) + extra_rp)
    return extra_rp

def compute_nodes_stretches(dst, V, E, iG, failures, stretch_stats):
    smax, avg = stretch_stats
    #for failed in itertools.combinations(E, failures):
    for i in xrange(min(num_paths_per_v, 1000)):
        #failedE = frozenset(failed)
        failedE = frozenset(random.sample(E, failures))
        for v in V:
            if dst != v and v.path.path is not None:
                rp = plinko_fwdtable_path(dst, v, failedE)
                shortest_p = shortest_path(V, E, iG, v, dst, failedE)

                # In the case where the network is
                # partitioned, it seems reasonable to report it as
                # actual path versus being dropped at the failure
                if shortest_p.path == None:
                    short_path_len = len(v.path.path)
                else:
                    short_path_len = len(shortest_p.path)
                actual_path_len = len(rp)

                #XXX: Hack to get the pathlen for hosts, not switches
                # Assumes that switches with one hosts are hosts themselves
                # for the rocketfuel.
                if v.numhosts > 1:
                    short_path_len += 2
                    actual_path_len += 2

                stretch = 1.0 * actual_path_len / short_path_len


                #heap.push(stretch)
                smax = max(smax, stretch)
                avg.update(stretch)
    return smax, avg

def main():
    # Create the parser and subparsers
    parser = argparse.ArgumentParser(
        description='Given a topology, compute state requirements assuming '
        'one of many different t-resilient routing algorithms')

    # Optionally accept a number of rounds to run for
    parser.add_argument('-r', '--rounds', default=sys.maxint, type=int,
        help='The number of rounds to compute backup routes for')

    # Table model - Plinko or FCP
    #parser.add_argument('--', default='edges', choices=('edges', 'vertices'),
    #    help='Build backup routes either for failed edges or failed vertices')

    # Fail either edges or vertices
    parser.add_argument('--fail', default='edges',
        choices=('edges', 'vertices', 'vert-and-last-edge'), #TODO: implement this
        help='Build backup routes either for failed edges or failed vertices')

    # Forwarding model
    parser.add_argument('--model', default='plinko',
        choices=('plinko', 'mpls-frr', 'eth-fcp'), #TODO: implement this
        help='The forwarding model to use. Plinko uses reverse paths, mpls-frr '
            'uses a unique path id, and eth-fcp uses a PAST tree with a failed '
            'edges label. eth-fcp should only be used with dst routing.')

    # Source or hop-by-hop routed
    parser.add_argument('--fwd-routing', default='src',
        choices=('src', 'hop-by-hop'), help='Forward paths are either source'
        'or hop-by-hop routed.')

    # Optionally write out all of the wildfwdtables
    parser.add_argument('-w', '--writetable',
        type=argparse.FileType('w'),
        help='Only output the forwarding table and do not compress, if '
            'applicable')

    # Compression aware routing
    parser.add_argument('-c', '--compression-aware-routing', action='store_true',
        help='Whether to perform compression aware routing or not.')

    # Enable deadlock-free routing (DFR)
    parser.add_argument('-d', '--dfr', action='store_true',
        help='Whether the routes should be deadlock-free or not.  If enabled, resilience is not guaranteed to be provided')

    #TODO: evaluate different size sets of hosts, say groups of 512-hosts per
    # 8K host topology

    #XXX: Stretch is being moved into a different file
    ## Optionally compute the stretch
    #parser.add_argument('-s', '--stretch', action='store_true',
    #    help='Compute the path stretch as well')

    # The input topology
    parser.add_argument('topo', type=argparse.FileType('r'),
        help='The YAML for the generated topology. MUST be syntactically \
        correct (e.g. the output from the topology generator (topo_gen.py)')

    # Parse the arguments
    args = parser.parse_args()
    topo = yaml.load(args.topo, Loader=yaml.CLoader)
    switches = topo['Switches']
    V, E = build_graph(switches)
    iG = mygraph_to_igraph(V, E)

    # Find the maximum number of hosts per switch
    #max_hosts_v = max(V, key=lambda x: x.numhosts)
    #print 'Maximum number of hosts per switch:', max_hosts_v.numhosts
    #sys.exit(1)

    # Verify the model and forward routing
    #if (args.model == 'eth-fcp' and args.fwd_routing == 'src'):
    #    print 'The eth-fcp model must only be used with dst forwarding '\
    #        'routing.'
    #    sys.exit(1)

    # Pick the destination
    Vlist = list(V)
    dst = random.choice(Vlist)
    #print dst

    #XXX: silly stretch stuff. remove this
    num_paths = int(len(V) * (len(V) - 1) * math.ceil(scipy.misc.comb(len(E), args.rounds)))
    global num_paths_per_v
    num_paths_per_v = num_paths / len(V)
    #stretch_heap = PercentileHeap(num_paths, 99.9)
    stretch_max = 0
    stretch_avg = IncAvg()
    total_stretch = []

    # Optionally create a global wildfwdtable
    firstglobalwrite = True
    globalwritetable = {}
    for v in V:
        globalwritetable[v.vnum] = []

    # Save the global (all-dst) state for each switch.
    global_tcam_state = {}
    tothosts = reduce(lambda acc, v: v.numhosts + acc, V, 0)
    #numhostsws = reduce(lambda v, acc: if v.numhosts > 0 acc + 1 else acc, V)
    #avg_hosts_per_sw = int(math.ceil(1.0 * tothosts / numhostsws))
    for v in V:
        sw_dst_bits = int(math.ceil(math.log(len(filter(
            lambda v: v.numhosts > 0, V)), 2)))
        hosts_dst_bits = int(math.ceil(math.log(tothosts, 2)))
        global_tcam_state[v.name] = {
            'sw_dst_bits': sw_dst_bits,
            'host_dst_bits': hosts_dst_bits,
            'port_bits': v.tot_ports,
            'sw_tcam': 0,
            'sw_tcam_unpacked': 0,
            'hosts_tcam': 0,
            'max_rp_bytes': 0,
            'avg_rp_unpacked_bytes': IncAvg(),
            'avg_rp_bytes': IncAvg(),
            'cam': 0,
            'hosts_cam': 0,
            'label_bits': 0,
        }

    for dst in V:
        # Quit if there are no destinations
        if dst.numhosts == 0:
            continue

        #print 'dst:', dst

        # Start a counter for the paths for MPLS-FRR.  The counter starts at 1
        # because 0 is reseved for paths entering the network
        nextPathId = itertools.count().next
        nextPathId() # 0 is reserved

        # Start a counter for the edge sets for ETH-FCP. Starts at 0 like normal.
        nextEdgeId = itertools.count().next

        # Build the init paths
        if args.model == 'eth-fcp' and args.fwd_routing == 'hop-by-hop':
            iT = build_tree(V, E, iG, dst)
            build_init_paths(V, dst, iT)
            # Init the table for storing trees for failed edges
            fwd_trees = {}
            eId = nextEdgeId()
            fwd_trees[frozenset()] = (eId, iT)
            eid_to_failed = {}
            eid_to_failed[eId] = frozenset()
            for v in V:
                v.path.firsthop_v_eid = (v, eId)
        else:
            build_init_paths(V, dst, iG)
            if args.model == 'eth-fcp':
                eId = nextEdgeId()
                fwd_trees = {frozenset(): (eId, None)}
                eid_to_failed = {eId: frozenset()}
                for v in V:
                    v.path.firsthop_v_eid = (v, eId)

        # Init the fwd tables
        for v in V:
            #XXX: Reset fwdtable and wildfwdtable.  Back hack for multiple dsts
            v.fwdtable = {}
            #v.rp_fwdtable = {} #XXX: Stretch
            v.wildfwdtable = []
            v.new_wildtable = []
            v.bitmask_wildtable = []
            v.tcam = []
            v.new_tcam = []
            v.newer_tcam = []
            v.member_trees = {}
        
        # Build the init fwd tables
        #flag = True
        for v in V:
            #XXX: DEBUGGING
            #if flag:
            #    print "src:", v
            #    flag = False
            #else:
            #    continue
            #print v.path
            if v.path.path is not None:
                assert(v.path.dst == dst)
                v.path.pid = nextPathId()
                if args.fwd_routing == 'src':
                    firste = v.edges[v.path.path[0]] if v.path.path is not None \
                        and len(v.path.path) > 0 else None
                    if args.model == 'plinko':
                        v.fwdtable[tuple(), firste, frozenset()] = v.path
                    elif args.model == 'mpls-frr':
                        # 0 is a special value to mean no MPLS label yet
                        v.fwdtable[0, firste, frozenset()] = v.path
                    elif args.model == 'eth-fcp':
                        if (0, frozenset()) not in v.member_trees:
                            # 0 is a special value to mean no Edge label yet
                            v.fwdtable[0, firste, frozenset()] = v.path
                            v.member_trees[0, frozenset()] = v.path
                elif args.fwd_routing == 'hop-by-hop':
                    curr = v
                    rp = deque()
                    for hop_i, hop in enumerate(v.path.path):
                        firste = curr.edges[hop]
                        assert(len(v.path.failedE) == 0)
                        assert(len(v.path.failedV) == 0)
                        currpath = Path(curr, [hop], v.path.failedE, rp,
                            v.path.failedV, fullPath = v.path.path[hop_i:])
                        currpath.pid = v.path.pid
                        if args.model == 'plinko':
                            curr.fwdtable[tuple(rp), firste, frozenset()] = \
                                currpath
                        elif args.model == 'mpls-frr':
                            if hop_i > 0:
                                curr.fwdtable[currpath.pid, firste, frozenset()] = \
                                    currpath
                            else:
                                curr.fwdtable[0, firste, frozenset()] = currpath
                        elif args.model == 'eth-fcp':
                            if (0, frozenset()) in curr.member_trees:
                                break
                            else:
                                curr.fwdtable[0, firste, frozenset()] = currpath
                                curr.member_trees[0, frozenset()] = currpath
                        ncurr, rhop = firste.get_other(curr, hop)
                        rp.appendleft(rhop)
                        curr = ncurr
                #XXX: Stretch
                #if tuple() not in v.rp_fwdtable:
                #    v.rp_fwdtable[tuple()] = {}
                #v.rp_fwdtable[tuple()][firste, frozenset()] = v.path

        # Build the initial edge dependencies
        dependencies = {}
        edgeDeps = frozenset()
        #flag = True
        for v in V:
            ##XXX: DEBUGGING
            #if flag:
            #    print "src:", v
            #    flag = False
            #else:
            #    continue
            if v.path.path is not None:
                #update_deps(dependencies, v.path, edgeDeps, args.fail)
                update_deps(dependencies, v.path, edgeDeps)

        i = 0
        while len(dependencies) > 0:
            #print 'Round %i' % i
            if i == args.rounds:
                break
            i += 1
            nextdep = {}
            for edgeDeps, paths in dependencies.iteritems():
                assert(len(edgeDeps) == i)
                for path in paths:
                    v, rpath = revpath_at_fail(path, edgeDeps)
                    fullRevPath = rpath + path.extraRPath
                    localFailedE, localFailedV = set(), set()
                    for port, edge in v.edges.iteritems():
                        if edge in edgeDeps:
                            localFailedE.add(edge)
                            localFailedV.add(edge.get_other(v, port)[0])
                    localFailedE = frozenset(localFailedE)
                    localFailedV = frozenset(localFailedV)
                    knownFailedE = path.failedE | localFailedE
                    knownFailedV = path.failedV | localFailedV
                    #print v, rpath, path, knownFailedE
                    assert(knownFailedE == edgeDeps)

                    if args.model == 'eth-fcp':
                        if args.fail == 'edges':
                            key = frozenset(path.failedE)
                            nkey = frozenset(knownFailedE)
                        elif args.fail == 'vertices':
                            key = frozenset(path.failedV)
                            nkey = frozenset(knownFailedV)
                        assert(len(key) + 1 == len(nkey))
                        assert(key in fwd_trees)
                        if nkey not in fwd_trees:
                            #iT = build_tree(V, E, iG, dst, knownFailedE,
                            #    knownFailedV, args.fail)
                            iT = None
                            neid = nextEdgeId()
                            fwd_trees[nkey] = (neid, iT)
                            eid_to_failed[neid] = nkey
                        eId, _ign = fwd_trees[key]
                        neId, iT = fwd_trees[nkey]

                    #XXX: Also add in a check to make sure that we don't add in
                    # backup paths for the edges that we already know are up from
                    # the reverse path

                    # Find the set of current Arcs we have used for DFR
                    # compression-aware routing
                    _v, fwdPath = reverse_path(v, fullRevPath)
                    arcSet = arc_set(_v, fwdPath)
                    #TODO: this assertion cannot be true until we don't add
                    # backup routes for edges that have already been traversed.
                    #assert(knownFailedE.isdisjoint(set(map(lambda x: x[1], arcSet))))

                    newpath = None
                    # Try to find an existing path in the forwarding table
                    #  that does not use any of the known failed edges
                    # XXX: Turns out, this is completely necessary
                    #if False:
                    #if args.fwd_routing == 'src':
                    #if args.compression_aware_routing and args.model == 'plinko':
                    if args.compression_aware_routing:
                        existing_paths = {}
                        for opath in v.fwdtable.itervalues():
                            # TODO: if DFR, then we must check it doesn't repeat any arcs
                            if opath is not None and \
                                    ((args.fail == 'edges' and \
                                      knownFailedE.isdisjoint(opath.edges)) or \
                                     (args.fail == 'vertices' and \
                                      knownFailedV.isdisjoint(opath.vertices))) and \
                                    (not args.dfr or arcSet.isdisjoint(opath.arcs)):
                                if args.dfr:
                                    assert (opath.arcs.isdisjoint(arcSet))
                                    # DEBUG
                                    #print 'compression-aware routing hit'
                                    #print 'arcSet:', arcSet, 'opath.arcs:', opath.arcs
                                    #print

                                assert(opath.dst == dst)
                                if args.fwd_routing == 'src':
                                    assert(opath.path == opath.fullPath)
                                # TODO: Right now we are choosing based on
                                # which full entire path through the network
                                # that is the most common.  Instead, it might
                                # be best in only the hop-by-hop case to choose
                                # the most in common first hop, and then just
                                # choose randomly from the possible fullpaths
                                # that that allows us.  I'll consider this later
                                if opath.fullPath not in existing_paths:
                                    existing_paths[opath.fullPath] = 0
                                existing_paths[opath.fullPath] += 1
                                # TODO: pick the *most* common existing path
                                # TODO: look at first fit as well?
                                #break
                        if len(existing_paths) > 0:
                            #print
                            #print 'existing_paths:', existing_paths
                            # Randomly pick between equal paths
                            existing_paths_l = existing_paths.items()
                            random.shuffle(existing_paths_l)
                            opath_path = max(existing_paths_l, key=lambda x: x[1])[0]
                            #print 'Using existing path %s' % str(opath_path)
                            newpath = Path(v, opath_path, knownFailedE, fullRevPath, knownFailedV)
                    if newpath is None:
                        if args.model == 'eth-fcp':
                            #iTopo = iT
                            iTopo = iG
                        else:
                            iTopo = iG
                        assert(path.rv == dst)
                        newpath = shortest_path(V, E, iTopo, v, path.rv,
                            knownFailedE, fullRevPath, knownFailedV, args.fail, args.dfr, arcSet)

                    newpath.pid = nextPathId()

                    if args.model == 'eth-fcp' and newpath.path is not None:
                        fhv, fheId = path.firsthop_v_eid
                        if v == fhv:
                            newpath.firsthop_v_eid = path.firsthop_v_eid
                        else:
                            newpath.firsthop_v_eid = (v, eId)

                    #XXX: Debugging
                    #print 'src:', v, 'dst:', dst, 'newpath:', newpath
                    #print 'knownFailedE', knownFailedE
                    #_tmpv, _tmprpath = revpath_at_fail(newpath, knownFailedE)
                    #assert(_tmpv == dst)

                    # Update the forwarding table
                    #XXX: Remove "None" paths from the fwdtable for now
                    if newpath.path is None:
                        continue
                    if args.fwd_routing == 'src':
                        firste = v.edges[newpath.path[0]] if newpath.path is not None else None
                        t_fullRevPath = tuple(fullRevPath)
                        if args.model == 'plinko':
                            v.fwdtable[(t_fullRevPath, firste, \
                                localFailedE)] = newpath
                        elif args.model == 'mpls-frr':
                            v.fwdtable[path.pid, firste, \
                                localFailedE] = newpath
                        elif args.model == 'eth-fcp':
                            _ign, fheId = newpath.firsthop_v_eid
                            #print 'fheId:', fheId, 'localFailedE', localFailedE
                            #print 'v:', v, 'member_trees:', v.member_trees
                            if (fheId, localFailedE) not in v.member_trees:
                                v.member_trees[fheId, localFailedE] = newpath
                                v.fwdtable[fheId, firste, \
                                    localFailedE] = newpath
                    elif args.fwd_routing == 'hop-by-hop':
                        curr = v
                        rp = deque(fullRevPath)
                        for hop_i, hop in enumerate(newpath.path):
                            # For eth-fcp
                            if hop in curr.edges:
                                firste = curr.edges[hop]
                                #print 'remaining path:', newpath.path[hop_i:]
                                currpath = Path(curr, [hop], newpath.failedE, rp,
                                    newpath.failedV, fullPath = newpath.path[hop_i:])
                                currpath.pid = newpath.pid
                            else:
                                firste = None
                                currpath = None

                            currLocalFailedE = frozenset(newpath.failedE & curr.edgeSet)
                            if args.model == 'plinko':
                                curr.fwdtable[tuple(rp), firste, \
                                currLocalFailedE] = currpath
                            elif args.model == 'mpls-frr':
                                if hop_i > 0:
                                    curr.fwdtable[currpath.pid, firste, \
                                        currLocalFailedE] = currpath
                                else:
                                    # XXX: BUG: the proper thing to do for a
                                    # path with multiple outputs at a switch is
                                    # to use the path.pid that first brought
                                    # the packet to the switch rather than
                                    # having chained paths at a single switch.
                                    # Doesn't affect state though, so I don't
                                    # care at the moment
                                    #XXX: Needs to be fixed before using with resnet_throughput.py
                                    curr.fwdtable[path.pid, firste, \
                                        currLocalFailedE] = currpath
                            elif args.model == 'eth-fcp':
                                if hop_i == 0:
                                    _ign, fheId = newpath.firsthop_v_eid
                                    #print 'fheId:', fheId, 'currLocalFailedE', currLocalFailedE
                                    #print 'curr:', curr, 'member_trees:', curr.member_trees
                                    if (fheId, currLocalFailedE) in curr.member_trees:
                                        if newpath.newpath == None:
                                            newpath.newpath = \
                                                list(newpath.path)
                                        #print 'len old path:', len(newpath.path)
                                        #print 'hop_i:', hop_i
                                        #print 'old_hop:', newpath.newpath[hop_i]
                                        newpath.newpath[hop_i] = \
                                            curr.member_trees[fheId, \
                                            currLocalFailedE].path[0]
                                        hop = newpath.newpath[hop_i]
                                        firste = curr.edges[hop]
                                        #print 'new_hop:', hop
                                    else:
                                        curr.member_trees[fheId, currLocalFailedE] = currpath
                                        curr.fwdtable[fheId, firste, \
                                            currLocalFailedE] = currpath
                                else:
                                    #print 'neId:', neId, 'currLocalFailedE', currLocalFailedE
                                    #print 'curr:', curr, 'member_trees:', curr.member_trees
                                    if (neId, currLocalFailedE) in curr.member_trees:
                                        if newpath.newpath == None:
                                            newpath.newpath = \
                                                list(newpath.path)
                                        #print 'len old path:', len(newpath.path)
                                        #print 'hop_i:', hop_i
                                        #print 'old_hop:', newpath.newpath[hop_i]
                                        newpath.newpath[hop_i] = \
                                            curr.member_trees[neId, \
                                            currLocalFailedE].path[0]
                                        hop = newpath.newpath[hop_i]
                                        firste = curr.edges[hop]
                                        #print 'new_hop:', hop
                                    else:
                                        curr.member_trees[neId, currLocalFailedE] = currpath
                                        curr.fwdtable[neId, firste, \
                                            currLocalFailedE] = currpath
                            #print 'actual hop:', hop
                            ncurr, rhop = firste.get_other(curr, hop)
                            rp.appendleft(rhop)
                            curr = ncurr

                    #XXX: Debug for no build_tree
                    if args.model == 'eth-fcp' and newpath.newpath != None:
                        _tmp_firsthop_v_eid = newpath.firsthop_v_eid
                        newpath = Path(newpath.v, newpath.newpath, \
                            newpath.failedE, newpath.extraRPath, \
                            newpath.failedV)
                        newpath.firsthop_v_eid = _tmp_firsthop_v_eid
                        assert(newpath.rv == dst)

                    #XXX: Stretch
                    #if t_fullRevPath not in v.rp_fwdtable:
                    #    v.rp_fwdtable[t_fullRevPath] = {}
                    #v.rp_fwdtable[t_fullRevPath][firste, localFailedE] = newpath

                    # Build the new dependencies
                    if newpath.path is not None:
                        #update_deps(nextdep, newpath, edgeDeps, args.fail)
                        update_deps(nextdep, newpath, edgeDeps)
            dependencies = nextdep

        def bitmask_from_new_table(table):
            new_table = table[:]
            for entry_i in xrange(len(new_table)):
                rule, path = new_table[entry_i]
                new_rule = []
                prefixlen = v.prefixlen
                for i in xrange(prefixlen):
                    if rule[i] == '*':
                        new_rule.extend(['*']*8)
                    else:
                        new_rule.extend(list('{0:08b}'.format(rule[i] if rule[i] >= 0 else 255)))
                new_rule.extend(rule[prefixlen:])
                new_table[entry_i] = (new_rule, path.path)
            return new_table


        # Get the label_bits 
        if args.model == 'mpls-frr':
            label_bits = int(math.ceil(math.log(nextPathId(), 2)))
        elif args.model == 'eth-fcp':
            label_bits = int(math.ceil(math.log(nextEdgeId(), 2)))

        # Compress the exact match forwarding table
        #XXX: Won't actually work!
        #if args.model == 'mpls-frr' or args.model == 'eth-fcp':
        #    pack_exact_match(V, label_bits)

        #for v in reversed(list(V)):
        for v in V:
            table_sizes = {}

            # Optionally start saving the wildfwdtable and ingore
            # compression
            if args.writetable:
                for key, path in v.fwdtable.iteritems():
                    #if path.path is None:
                    #    global_entry = [dst.vnum, list(rpath), list(mask), None]
                    if path.path is not None:
                        key1, e, lf = key
                        ae = e.enum
                        alf = [e.enum for e in lf]
                        if args.model == 'eth-fcp':
                            assert (args.fail != 'vertices')
                            tkey1 = eid_to_failed[key1]
                            akey1 = [e.enum for e in tkey1]
                            ankey = [e.enum for e in path.failedE]
                            global_entry = [[dst.vnum, akey1, ae, alf],
                                list(path.path)]
                                #[list(path.path), ankey]] #XXX: use this for more accuracy.  Currently resnet_throughput.py just implies ankey
                        elif args.model == 'plinko':
                            akey1 = list(key1)
                            global_entry = [[dst.vnum, akey1, ae, alf],
                                list(path.path)]
                    globalwritetable[v.vnum].append(global_entry)
                continue

            if args.model == 'mpls-frr':
                # DEBUG: Printing for debugging
                #print '%s:' % v
                #for (pid, e, f), out in v.fwdtable.iteritems():
                #    print '\t%s,\t%s\t%s -> %s (%s)' % (pid, e, f, out.pid, out.path)

                # Output the global sizes
                camsize = len(v.fwdtable)
                hosts_cam = camsize * dst.numhosts
                global_tcam_state[v.name]['cam'] += camsize
                global_tcam_state[v.name]['hosts_cam'] += hosts_cam
                old_label_bits = global_tcam_state[v.name]['label_bits']
                global_tcam_state[v.name]['label_bits'] = \
                    max(label_bits, old_label_bits)

                # Compress the forwarding table

                continue
            elif args.model == 'eth-fcp':
                camsize = len(v.fwdtable)
                hosts_cam = camsize * dst.numhosts
                global_tcam_state[v.name]['cam'] += camsize
                global_tcam_state[v.name]['hosts_cam'] += hosts_cam
                old_label_bits = global_tcam_state[v.name]['label_bits']
                global_tcam_state[v.name]['label_bits'] = \
                    max(label_bits, old_label_bits)

                # Compress the forwarding table

                continue


                #DEBUG: Printing for debugging
                #print 'dst: %s:' % v
                #for (eid, e, f), out in v.fwdtable.iteritems():
                #    print '\t%s,\t%s\t%s -> %s' % (eid, e, f,  out.path)
                continue

            # Update the average prefixlen
            for (rpath, uplink, lfE), path in v.fwdtable.iteritems():
                global_tcam_state[v.name]['avg_rp_unpacked_bytes'].update(len(rpath))

            build_wild_table(v)
            #print_wildfwdtable(v)
            if not check_wildfwdtable(v):
                print 'ERROR! Invalid wildfwdtable!'
                print_wildfwdtable(v)
                sys.exit(1)
            v.prefixlen = len(v.wildfwdtable[0][0]) if len(v.wildfwdtable) > 0 else 0
            table_sizes['prefixlen'] = v.prefixlen
            table_sizes['wildfwdtable'] = len(v.wildfwdtable)
            #table_sizes['cam'] = count_total_entries(v)
            #TODO: Entry bytes is more pessimistic than entry bits
            #table_sizes['entry_bytes'] = v.dstbytes + v.prefixlen + \
            #    int(math.ceil((v.tot_ports / 8.0)))

            #XXX HACK: Reclaim memory
            v.fwdtable = {}

            v.new_wildtable = map(lambda x: (x[0] + tuple(x[1]), x[2]),
                v.wildfwdtable)
            #XXX: Disable debugging
            if not check_new_wildtable(v.new_wildtable):
                print 'ERROR! Invalid new_wildtable!'
                print_new_table(v, v.new_wildtable)
                sys.exit(1)
            table_sizes['new_wildtable'] = len(v.new_wildtable)

            v.bitmask_wildtable = map(lambda x: (map(lambda y: list('{0:08b}'.format(y)), map(lambda z: z if z >= 0 else 255, x[0])), x[1], x[2]), v.wildfwdtable)
            v.bitmask_wildtable = map(lambda x: (reduce(lambda y, z: y + z, x[0]) + list(x[1]), x[2].path), v.bitmask_wildtable)

            #XXX HACK: Reclaim memory
            v.wildfwdtable = []

            #bw_wildtable = bitweave.BitWeave(v.bitmask_wildtable)
            #if not new_check_table(v.bitmask_wildtable, bw_wildtable):
            #    print 'ERROR! BitWeaving is incorrect!'
            #    sys.exit(1)
            #table_sizes['bw_wildtable'] = len(bw_wildtable)

            #XXX HACK: Reclaim memory
            #v.bitmask_wildtable = []

            #pack_lpm(v)
            #pack_tcam(v)
            #if not check_tcam(v):
            #    print_wildfwdtable(v)
            #    print_tcam(v)
            #    sys.exit(1)
            #table_sizes['lpm_wildtable'] = len(v.lpm_wildtable)
            #table_sizes['lpm'] = len(v.lpm)
            #table_sizes['lpm_tcam'] = len(v.new_lpm_tcam)

            """
            v.new_tcam = new_pack_tcam(v.new_wildtable)
            #print_new_table(v, v.new_tcam)
            #XXX: Disable debugging
            #if not new_check_tcam(v):
            #    print 'ERROR! New TCAM is incorrect!'
            #    print_new_table(v, v.new_wildtable)
            #    print_new_table(v, v.new_tcam)
            #    sys.exit(1)
            table_sizes['new_tcam'] = len(v.new_tcam)
            #table_sizes['new_tcam_bytes'] = bytes_new_table(v, v.new_tcam)

            #XXX: output for creating an example
            print 'New Wild Table:'
            print_new_table(v, v.new_wildtable)
            print 'New TCAM:'
            print_new_table(v, v.new_tcam)
            if not new_check_tcam(v):
                print 'ERROR! New TCAM is incorrect!'
                #sys.exit(1)

            # Update the average prefixlen
            entry_lens = new_tcam_entry_lens(v)
            assert(len(v.new_tcam) == len(entry_lens) + 1)
            for rplen in entry_lens:
                global_tcam_state[v.name]['avg_rp_bytes'].update(rplen)
            entry_lens = []

            #if len(v.new_tcam) > 1:
            #    # Build the string bit version of the new_tcam
            #    bitmask_new_tcam = bitmask_from_new_table(v.new_tcam)
            #
            #    # BitWeave the bitmask_new_tcam
            #    bw_new_tcam = bitweave.BitWeave(bitmask_new_tcam)
            #    #XXX: Disable debugging
            #    if not new_check_table(v.bitmask_wildtable, bw_new_tcam):
            #        print_new_table(v, bitmask_new_tcam)
            #        print_new_table(v, bw_new_tcam)
            #        print 'ERROR! BitWeaving is incorrect!'
            #        sys.exit(1)
            #    table_sizes['bw_new_tcam'] = len(bw_new_tcam)
            #    #table_sizes['bw_new_tcam_bytes'] = bytes_bw_table(v.bitmask_wildtable, bw_new_tcam, v.prefixlen * 8)
            #
            #    #XXX HACK: Reclaim memory
            #    bitmask_new_tcam = []
            #    bw_new_tcam = []
            #    v.bitmask_wildtable = []
            #else:
            #    table_sizes['bw_new_tcam'] = 0
            #    table_sizes['bw_new_tcam_bytes'] = 0

            #XXX HACK: Reclaim memory
            v.new_tcam = []
            """

            v.newer_tcam = newer_pack_tcam(v.new_wildtable)
            if not newer_check_tcam(v):
                print 'ERROR! Newer TCAM is incorrect!'
                print_new_table(v, v.new_wildtable)
                print_new_table(v, v.newer_tcam)
                sys.exit(1)
            table_sizes['newer_tcam'] = len(v.newer_tcam)

            # Update the average prefixlen
            entry_lens = newer_tcam_entry_lens(v)
            #print len(v.newer_tcam), len(entry_lens)
            #assert(len(v.newer_tcam) == len(entry_lens))
            for rplen in entry_lens:
                global_tcam_state[v.name]['avg_rp_bytes'].update(rplen)
            entry_lens = []

            #XXX: output for creating an example
            #print 'New Wild Table:'
            #print_new_table(v, v.new_wildtable)
            #print 'Newer TCAM:'
            #print_new_table(v, v.newer_tcam)
            #if not newer_check_tcam(v):
            #    print 'ERROR! Newer TCAM is incorrect!'
            #    #sys.exit(1)

            #XXX HACK: Reclaim memory
            v.new_wildtable = []

            # Build the string bit version of the newer_tcam
            #bitmask_newer_tcam = bitmask_from_new_table(v.newer_tcam)

            #XXX HACK: Reclaim memory
            v.newer_tcam = []

            """
            #XXX: Disabled because bitweaving doesn't often significantly reduce space
            # BitWeave the bitmask_newer_tcam
            bw_newer_tcam = bitweave.BitWeave(bitmask_newer_tcam)
            #if not new_check_table(v.bitmask_wildtable, bw_new_tcam):
            #    print_new_table(v, bitmask_new_tcam)
            #    print_new_table(v, bw_new_tcam)
            #    print 'ERROR! BitWeaving is incorrect!'
            #    sys.exit(1)
            table_sizes['bw_newer_tcam'] = len(bw_newer_tcam)

            #XXX HACK: Reclaim memory
            bitmask_newer_tcam = []
            bw_newer_tcam = []
            """

            #print_wildfwdtable(v)
            #print_new_table(v, v.new_wildtable)
            #print_tcam(v)
            #print_new_table(v, v.new_tcam)
            #print_new_table(v, v.new_lpm_tcam)

            #table_sizes['tcam'] = len(v.tcam)

            # Find the number of entries if built per-host
            table_strs = ('newer_tcam', 'bw_newer_tcam', 
                          'new_tcam', 'bw_new_tcam', 'cam') 
            mintable = min([val for table, val in table_sizes.items() if \
                            table in table_strs])
            # Remove the drop rule
            if mintable > 0:
                mintable -= 1
            hosts_tcam = mintable * dst.numhosts
            table_sizes['hosts_tcam'] = hosts_tcam

            # Output the global sizes
            global_tcam_state[v.name]['sw_tcam'] += mintable
            global_tcam_state[v.name]['sw_tcam_unpacked'] += \
                table_sizes['wildfwdtable']
            global_tcam_state[v.name]['hosts_tcam'] += hosts_tcam
            #global_tcam_state[v.name]['cam'] += table_sizes['cam']
            old_bytes = global_tcam_state[v.name]['max_rp_bytes']
            global_tcam_state[v.name]['max_rp_bytes'] = \
                max(table_sizes['prefixlen'], old_bytes)

        # Compute the path stretch
        #if args.stretch:
        #    stretch_max, stretch_avg = \
        #        compute_nodes_stretches(dst, V, E, iG, args.rounds,
        #            (stretch_max, stretch_avg))

        ## Print the YAML output to stdout
        #print '%s:' % dst
        #outputstr = yaml.dump(output, default_flow_style=False, indent=4)
        #for line in outputstr.split('\n'):
        #    print '    %s' % line

        # Write and reset the globalwritetable to save memory
        if args.writetable:
            if firstglobalwrite:
                firstglobalwrite = False
                args.writetable.write('[\n')
            else:
                args.writetable.write(',')
            for chunk in jsone.iterencode(globalwritetable):
                args.writetable.write(chunk)
            globalwritetable = {}
            for v in V:
                globalwritetable[v.vnum] = []


    for vname in global_tcam_state:
        global_tcam_state[vname]['avg_rp_unpacked_bytes'] = \
            global_tcam_state[vname]['avg_rp_unpacked_bytes'].get()
        global_tcam_state[vname]['avg_rp_bytes'] = \
            global_tcam_state[vname]['avg_rp_bytes'].get()

    outstr = yaml.dump(global_tcam_state, default_flow_style=False, indent=4)
    print outstr

    # Write the wildtable, if requested
    if args.writetable:
        args.writetable.write(']\n')
        #for chunk in jsone.iterencode(globalwritetable):
        #    args.writetable.write(chunk)
        #yaml.dump(globalwritetable, args.writetable, Dumper=Dumper)

    # Print the stretch statistics
    #if args.stretch:
    #    print 'stretch:'
    #    print '    max: %f' % stretch_max
    #    print '    avg: %f' % stretch_avg.get()
    #    #print '    99.9p: %f' % stretch_heap.get_percentile()

    #XXX: Verify the smaller statistics
    #total_avg = 1.0 * sum(total_stretch) / len(total_stretch)
    #incavg = stretch_avg.get()
    #print 'total_avg', total_avg, 'incavg', incavg
    #assert(total_avg - incavg < 0.00001)
    #total_per = scipy.stats.scoreatpercentile(total_stretch, 99)
    #incper = stretch_heap.get_percentile()
    #print 'total_per', total_per, 'incper', incper
    #assert(total_per == incper)

    # Fail every single link
    #for i in xrange(1, len(E) + 1):
    #for i in xrange(1, 2):
    #    for edges in itertools.combinations(E, i):
    #        #XXX: This list manipulation can't be fast
    #        edges = list(edges)
    #        edges.sort()
    #        edges = tuple(edges)

if __name__ == "__main__":
    main()
