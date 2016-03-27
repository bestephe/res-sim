#!/usr/bin/env python

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
import math
import random
import socket
import struct
import sys
import yaml

def prod(iterable):
    return reduce(lambda x, y: x * y, iterable, 1)

def get_hosts(args):
    if args.num_hosts != None:
        hosts = [socket.inet_ntoa(struct.pack('!i', i)) for i in range(1, args.num_hosts+1)]
    else:
        hosts = yaml.load(args.host_file)
        args.num_hosts = len(hosts)
    return hosts

def is_host(str):
    if str.startswith('host'):
        return True
    try:
        socket.inet_aton(str)
        return True
    except socket.error:
        return False

def output_devices(output, devices, is_host=lambda x: False):
    hosts = [dev for dev in devices if is_host(dev)]
    hosts.sort()
    hosts_set = set(hosts)
    num_hosts = len(hosts)
    switches = [dev for dev in devices if dev not in hosts_set]
    switches.sort(lambda x,y: cmp(len(devices[y]), len(devices[x])))
    switches.sort()

    class Switch:
        def __init__(self, name):
            self.name = name
            self.ports = {}

        # This is dumb for a few reasons, but I don't want to fix it now.
        #  Reason 1) No reason to iterate over the list
        #  Reason 2) I shouldn't assume bidirectional links.  However, if
        #   this is generating Ethernet-like topologies, then bidirectional
        #   links is correct, so I'm leaving this as is for now.
        def add_port(self, other):
            selfp = len(self.ports)
            for selfp in xrange(len(devices[self.name])):
                if devices[self.name][selfp] == other.name and \
                    selfp not in self.ports:
                        break
            assert (selfp != len(devices[self.name]))
            assert (selfp not in self.ports)

            for otherp in xrange(len(devices[other.name])):
                if devices[other.name][otherp] == self.name and \
                    otherp not in other.ports:
                        break
            assert(otherp != len(devices[other.name]))
            assert (otherp not in other.ports)

            self.ports[selfp] = '%s port %d' % (other.name, otherp)
            other.ports[otherp] = '%s port %d' % (self.name, selfp)

        def serialize(self):
            d = {self.name: {'ports': self.ports}}
            return d

    devs_d = {name: Switch(name) for name in devices}

    # processed_sws should be removed if we're not assuming bidirectional
    # topologies.  This can be changed later.
    processed_sws = set()
    for swname in switches:
        processed_sws.add(swname)
        sw = devs_d[swname]
        for otherdevname in devices[swname]:
            if otherdevname not in processed_sws:
                otherdev = devs_d[otherdevname]
                sw.add_port(otherdev)

    #XXX: (Lightly) validate the topology
    for swname in switches:
        sw = devs_d[swname]
        otherdevs = devices[swname]
        for port, othername in enumerate(otherdevs):
            assert(sw.ports[port].find(othername) >= 0)
        assert (len(otherdevs) == len(sw.ports))
            
    sw_yaml = [devs_d[swname].serialize() for swname in switches]
    yaml_data = {'Switches': sw_yaml}

    # Dump YAML data
    yaml.dump(yaml_data, output, default_flow_style=False, \
        explicit_start=True)

def egft(args):
    L, M, C, K = args.tuple
    if len(M) != L or len(C) != L or len(K) != L:
        raise ValueError("M, C, and K must be of length L!")

    num_switches = sum([prod(M[i+1:]) * prod(C[:i+1]) for i in range(L)])
    hosts = get_hosts(args)
    num_hosts = len(hosts)
        
    # Init devices
    switches = []
    levels = {}
    for i in range(1, L+1):
        level = []
        indices = C[:i] + M[i:]
        num_level_sw = prod(C[:i]) * prod(M[i:])
        for level_sw in range(num_level_sw):
            swaddr = []
            for digit in range(L):
                level_sw, r = divmod(level_sw, indices[digit])
                prefix = 'c' if digit < i else 'm'
                swaddr.append(prefix + str(r))
            level.append(swaddr)
            swname = 'switch.' + '.'.join(swaddr)
            switches.append(swname)
        if i < L:
            levels[i] = level
    devices = dict([(dev, []) for dev in switches])
    devices.update(dict([(dev, []) for dev in hosts]))

    # Connect switches
    for lnum, levelsws in levels.iteritems():
        for swaddr in levelsws:
            swname = 'switch.' + '.'.join(swaddr)
            for i in range(C[lnum]):
                for j in range(K[lnum]):
                    o_swaddr = list(swaddr)
                    o_swaddr[lnum] = 'c' + str(i)
                    o_swname = 'switch.' + '.'.join(o_swaddr)
                    devices[swname].append(o_swname)
                    devices[o_swname].append(swname)

    # Add hosts to the level 1 switches
    level1 = levels[1]
    for sw_i in range(len(level1)):
        swaddr = level1[sw_i]
        switch = 'switch.' + '.'.join(swaddr)
        try:
            hosts_per_sw = (num_hosts+sw_i)/len(level1)
            for i in range(hosts_per_sw):
                host = hosts.pop(0)
                devices[switch].append(host)
                devices[host].append(switch)
        except IndexError:
            break

    if len(hosts) > 0:
        raise ValueError('Topology not large enough! %d hosts left' \
            % len(hosts))
        
    return devices

def hyperx(args):
    L, S, K, T = args.tuple
    if len(S) != L or len(K) != L:
        raise ValueError("S and K must be of length L!")

    num_switches = prod(S)
    hosts = get_hosts(args)
    num_hosts = len(hosts)

    # Init devices
    switches = []
    for num in range(num_switches):
        swaddr = []
        for digit in range(L):
            num, r = divmod(num, S[digit])
            swaddr.append(str(r))
        switches.append('switch.' + '.'.join(swaddr))
    devices = dict([(dev, []) for dev in switches])
    devices.update(dict([(dev, []) for dev in hosts]))

    # Connect switches
    for sw in switches:
        swaddr = sw.split('.')[1:]
        for i in range(len(swaddr)):
            for si in range(S[i]):
                for j in range(K[i]):
                    o_swaddr = list(swaddr)
                    o_swaddr[i] = str(si)
                    o_sw = 'switch.' + '.'.join(o_swaddr)
                    if o_sw != sw:
                        devices[sw].append(o_sw)

    # Add hosts to switches
    for switch_i in range(len(switches)):
        switch = switches[switch_i]
        try:
            hosts_per_sw = (num_hosts+switch_i)/num_switches
            for i in range(hosts_per_sw):
                host = hosts.pop(0)
                devices[switch].append(host)
                devices[host].append(switch)
        except IndexError:
            break

    if len(hosts) > 0:
        raise ValueError('Topology not large enough! %d hosts left' \
            % len(hosts))

    return devices

def optimal(args):
    hosts = get_hosts(args)

    # Init devices
    switch = 'switch0'
    switches = [switch]
    devices = dict([(dev, []) for dev in switches])
    devices.update(dict([(dev, []) for dev in hosts]))

    # Add hosts to switches
    for host in hosts:
        devices[switch].append(host)
        devices[host].append(switch)

    return devices

def jellyfish(args):
    N = args.N
    k = args.k
    r = args.r
    hosts = get_hosts(args)

    # Init devices
    switches = ['switch%d' % i for i in range(N)]
    devices = dict([(dev, []) for dev in switches])
    devices.update(dict([(dev, []) for dev in hosts]))

    """ I) Start with a set U of N*r ports
        II) Choose two random ports i and j in U, from switches I and
            J, and connect them if I != J and I and J are not already
            connected.
    """
    def connect_ports(switches, devices):
        U = [sw for x in range(r) for sw in switches]
        links = []
        index = 0
        while len(U) > 0:
            index += 1
            if index >= 100000:
                break
            if len(U) == 2 and (U[0] == U[1] or U[0] in devices[U[1]]):
                break
            i, j = random.choice(U), random.choice(U)
            if i != j and i not in devices[j] and j not in devices[i]:
                U.remove(i)
                U.remove(j)
                devices[i].append(j)
                devices[j].append(i)
                links.append((i, j))

        #XXX: Hack for if N is less than r
        if len(U) > 0 and N < r:
            while len(U) > 0:
                if len(U) == 2 and U[0] == U[1]:
                    break
                i, j = random.choice(U), random.choice(U)
                # Check to see if there is just one switch left
                if all(map(lambda x: i == x, U)):
                    print 'Quitting with %d ports on switch %s left' % (len(U), i)
                    break
                if i != j:
                    U.remove(i)
                    U.remove(j)
                    devices[i].append(j)
                    devices[j].append(i)
                    links.append((i, j))

        # Failover to incremental expansion
        if len(U) > 0:
            print 'Incremental Expansion: %d remaining ports' % len(U)
            def count_rem_ports(d, v):
                if v in d:
                    d[v] += 1
                else:
                    d[v] = 1
                return d
            remsws = reduce(count_rem_ports, U, {})
            for sw, numports in remsws.iteritems():
                while numports >= 2:
                    i, j = random.choice(links)
                    while i is sw or j is sw or i in devices[sw] \
                            or j in devices[sw]:
                        i, j = random.choice(links)
                    devices[i].remove(j)
                    devices[j].remove(i)
                    devices[i].append(sw)
                    devices[sw].append(i)
                    links.append((i, sw))
                    devices[j].append(sw)
                    devices[sw].append(j)
                    links.append((j, sw))
                    numports -= 2

        return True

    # Connects ports
    while connect_ports(switches, devices) == False:
        # Reset devices
        devices = dict([(dev, []) for dev in switches])
        devices.update(dict([(dev, []) for dev in hosts]))

    # Sort Port lists
    for l in devices.itervalues():
        l.sort()

    # Add hosts to switches
    for switch_i in range(len(switches)):
        switch = switches[switch_i]
        try:
            for i in range((args.num_hosts+switch_i)/N):
                host = hosts.pop(0)
                devices[switch].append(host)
                devices[host].append(switch)
        except IndexError:
            break

    if len(hosts) > 0:
        raise ValueError('Topology not large enough! %d hosts left' \
            % len(hosts))

    return devices
	
def main():
    # Create the parser and subparsers
    parser = argparse.ArgumentParser(
        description='Generate a topology')
    subparsers = parser.add_subparsers()

    # Optionally accept an output file
    parser.add_argument('-o', '--output', default=sys.stdout, \
        type=argparse.FileType('w'), \
        help='The YAML output file for the generated topology.  Defaults to stdout')

    # The hosts can either be generated or come from a file
    hosts_group = parser.add_mutually_exclusive_group(required=True)
    hosts_group.add_argument('--num-hosts', type=int, \
        help='The total number of hosts to add to the topology')
    hosts_group.add_argument('--host-file', type=argparse.FileType('r'), \
        help='A file containing a list of hosts to add to the topology')

    # Create a subparser for the EGFT topology
    parser_egft = subparsers.add_parser('egft', help='EGFT \
        topology.')
    parser_egft.set_defaults(func=egft)
    parser_egft.add_argument('tuple', type=eval, help='A four-tuple \
        (L,M,C,K) that desribes the EGFT topology.  L is the number \
        of levels, M is a vector that describes the number of children \
        at a level, C is a vector that describes the number of parents \
        at a level, and K is the link aggregation vector.')

    # Create a subparser for the HyperX topology
    parser_hyperx = subparsers.add_parser('hyperx', help='HyperX \
        topology.')
    parser_hyperx.set_defaults(func=hyperx)
    parser_hyperx.add_argument('tuple', type=eval, help='A four-tuple \
        (L,S,K,T) that desribes the HyperX topology.  L is the number \
        of dimensions, S is a vector that describes the number of switches \
        in each dimension, K is the link aggregation vector, and T is the \
        number of hosts per switch.')

    # Create a subparser for the optimal topology
    parser_optimal = subparsers.add_parser('optimal',   \
        help='Optimal non-blocking network.  Simply a single switch.')
    parser_optimal.set_defaults(func=optimal)

    # Create a subparser for the Jellyfish topology
    parser_jellyfish = subparsers.add_parser('jellyfish', \
        help='Jellyfish topology. A RRG(N, k, r), where each of the N \
        switches has k ports, r of which connect to other switches. \
        Bisection bandwidth is min((r/2 - sqrt(r*ln(2)))/(k - r), 1).')
    parser_jellyfish.set_defaults(func=jellyfish)
    parser_jellyfish.add_argument('-N', type=int, required=True)
    parser_jellyfish.add_argument('-k', type=int, required=True)
    parser_jellyfish.add_argument('-r', type=int, required=True)

    # Parse the arguments
    args = parser.parse_args()
    devices = args.func(args)
    output_devices(args.output, devices, is_host)
    args.output.close()

if __name__ == "__main__":
    main()
