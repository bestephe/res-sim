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

import argparse
import numpy
from numpy import asscalar as scal
import yaml
from scipy.misc import comb
from resnet_alg import *

res = [0, 1, 2, 4, 6, 8]

def estimate_src_helper(V, r, avg_plen):
    dsts = len([v for v in V if v.numhosts > 0])
    if r == 0:
        return (dsts -1) * (avg_plen ** r)
    else:
        return 1.0 * dsts * (dsts - 1) / len(V) * (avg_plen ** r)

def estimate_src(V, r, avg_plens):
    rounds = [estimate_src_helper(V, r, avg_plens[r]) for r in range(r + 1)]
    #print rounds
    return sum(rounds)

def estimate_hbh(V, r, avg_plens):
    dsts = len([v for v in V if v.numhosts > 0])
    rounds = [1.0 * dsts * (dsts - 1) / len(V) * ((avg_plens[r]) ** (r + 1)) for r in range(r + 1)]
    #print rounds
    return sum(rounds)

def avg_pathlen(V, E, iG, r):
    # Get the srcs and dsts
    dsts = [v for v in V if v.numhosts > 0]
    srcs = dsts if r == 0 else V

    # Set up the loop
    avg_pathlen = IncAvg()
    num_iters = 30 if r > 0 else 1
    
    for _i in xrange(num_iters):
        failedE = frozenset(random.sample(E, r))
        for src in srcs:
            for dst in dsts:
                if src != dst:
                    path = shortest_path(V, E, iG, src, dst, failedE)
                    assert(path.path != None)
                    avg_pathlen.update(len(path.path))

    print 'r:', r, 'avg_pathlen:', avg_pathlen.get()
    return avg_pathlen.get()
            

def main():
    # Create the parser
    parser = argparse.ArgumentParser(
        description='Given an average path len ap and a level of resiliency, '
        'compute the expected state per switch with mpls-frr routing')

    # The longest path
    parser.add_argument('-a', '--ap', type=float, required=True,
        help='The average path in a forwarding table.')

    # The input topology
    parser.add_argument('--topo', type=argparse.FileType('r'), required=True,
        help='The YAML for the generated topology. MUST be syntactically \
        correct (e.g. the output from the topology generator (topo_gen.py)')

    # Fail either edges or vertices
    #parser.add_argument('--fail', default='edges',
    #    choices=('edges', 'vertices'), #TODO: implement this
    #    help='Build backup routes either for failed edges or failed vertices')

    # The level of resiliency
    #parser.add_argument('-r', type=int, required=True,
    #    help='The level of resiliencey provided. -1 for perfect (shortest path) routing')

    # The total number of edges in the network
    #parser.add_argument('-E', type=int, required=True,
    #    help='The number of the edges in the topology.')

    # Parse the arguments
    args = parser.parse_args()

    # Parse the topo
    topo = yaml.load(args.topo, Loader=yaml.CLoader)
    switches = topo['Switches']
    V, E = build_graph(switches)
    iG = mygraph_to_igraph(V, E)

    #args.ap = iG.average_path_length()
    #print 'avg_pathlen:', args.ap

    #avg_pathlens = {r: avg_pathlen(V, E, iG, r) for r in res}
    avg_pathlens = {0: 2.0, 1: 1.6595744680851185, 2: 1.6595744680851185,
       3: 1.6595744680851185, 4: 1.6595744680851185, 5: 1.6595744680851185,
       6: 1.6595744680851185, 7: 1.6595744680851185,  8: 1.6597074468085091}
    print yaml.dump({'avg_pathlens': avg_pathlens})

    # Compute the probability that a fail will cause a loss for vertices
    src_state = {r: estimate_src(V, r, avg_pathlens) for r in res}
    hbh_state = {r: estimate_hbh(V, r, avg_pathlens) for r in res}

    output = {'src_state': src_state, 'hbh_state': hbh_state}
    print yaml.dump(output)

if __name__ == "__main__":
    main()
