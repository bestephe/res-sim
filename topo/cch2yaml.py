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
import sys
import fnss
import networkx as nx
import topo_gen

def parse_cch(fname):
    topo = fnss.parse_rocketfuel_isp_map(fname)
    topo = topo.to_undirected()

    components = nx.connected_component_subgraphs(topo)
    cmpnodes = lambda x, y: x if x.number_of_nodes() > y.number_of_nodes() else y
    largest_g = reduce(cmpnodes,  components)

    devices = {}
    for node, nbrs in largest_g.adjacency_iter():
        nid = 'uid_' + str(node)
        devices[nid] = []
        for nbr in nbrs:
            nbr_id = 'uid_' + str(nbr)
            devices[nid].append(nbr_id)
    return devices

def main():
    # Create the parser
    parser = argparse.ArgumentParser(
        description='Convert RocketFuel .cch files into our .yaml format')

    # Optionally accept an output file
    parser.add_argument('-o', '--output', default=sys.stdout, \
        type=argparse.FileType('w'), \
        help='The YAML output file for the generated topology.  Defaults to stdout')

    # The minimum bisection bandwidth of the network
    parser.add_argument('cchfile', help='The .cch topology to convert')

    # Parse the arguments
    args = parser.parse_args()
    devices = parse_cch(args.cchfile)
    topo_gen.output_devices(args.output, devices)

if __name__ == "__main__":
    main()
