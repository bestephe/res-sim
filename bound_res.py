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

fails = [1, 4, 16, 64, 256]
#fails = [1, 2, 4, 8, 16]

def estimate(E, r, f, lp):
    if f <= r:
        return 0.0
    if E - f < lp:
        return 1.0
    probs = [(1 - (1.0 * scal(comb(E - f, lp)) / scal(comb(e, lp)))) for e in range(E, E - (r+ 1), -1)]
    return reduce(lambda x, y: x * y, probs, 1.0)
    
    #return (1 - (1.0 * scal(comb(E - f, lp)) / scal(comb(E, lp)))) ** (r + 1)

def est_pcnt_hosts_fail(V, f):
    #num_hosts = reduce(lambda acc, v: acc + v.numhosts, V, 0)
    #hosts_per_switch = 1.0 * num_hosts / len(V)
    #print hosts_per_switch
    if f > V:
        return 1.0
    percent_src_failed = 1.0 * f / V
    #percent_dst_failed = 
    return percent_src_failed + (1.0 - percent_src_failed) * percent_src_failed

def main():
    # Create the parser
    parser = argparse.ArgumentParser(
        description='Given a longest path len lp and a level of resiliency, '
        'compute the probability that uncorrelated uniform failures will cause a '
        'failure')

    # The longest path
    parser.add_argument('-l', '--lp', type=float, required=True,
        help='The longest path in a forwarding table.')

    # The input topology
    parser.add_argument('--topo', type=argparse.FileType('r'), required=True,
        help='The YAML for the generated topology. MUST be syntactically \
        correct (e.g. the output from the topology generator (topo_gen.py)')

    # Fail either edges or vertices
    parser.add_argument('--fail', default='edges',
        choices=('edges', 'vertices'), #TODO: implement this
        help='Build backup routes either for failed edges or failed vertices')

    # The level of resiliency
    parser.add_argument('-r', type=int, required=True,
        help='The level of resiliencey provided. -1 for perfect (shortest path) routing')

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

    # Compute the probability that a fail will cause a loss for vertices
    if args.fail == 'vertices':
        if args.r < 0:
            prob = [est_pcnt_hosts_fail(len(V), f) for f in fails]
        else:
            prob = [1.0 - ((1.0 - estimate(len(V), args.r, f, args.lp - 1)) * \
                (1.0 - est_pcnt_hosts_fail(len(V), f))) for f in fails]
    else:
        if args.r < 0:
            'Perfect resilience for edge resilience is not yet implemented'
        prob = [estimate(len(E), args.r, f, args.lp) for f in fails]
    prob = dict(zip(fails, prob))
    print yaml.dump(prob)

if __name__ == "__main__":
    main()
