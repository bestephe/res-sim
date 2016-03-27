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
import itertools
import math
import sys

import factorize

def prod(iterable):
    return reduce(lambda x, y: x * y, iterable, 1)

class HyperX(object):
    def __init__(self, S):
        self.L = len(S)
        self.S = tuple(S)
        self.K = tuple([0 for i in range(len(S))])
        self.T = 1
        self.numsw = prod(S)
    def __str__(self):
        return '[L=%d, S=%s, K=%s, T=%d]' % \
            (self.L, str(self.S), str(self.K), self.T)
    def __repr__(self):
        return '(%d, %s, %s, %d)' % \
            (self.L, str(list(self.S)), str(list(self.K)), self.T)

def hyperx_opt(args):
    hosts = args.numhosts
    bisec = args.bisec
    radix = args.radix

    topos = []
    for L in range(1, 15):
        S = [2 for i in range(L)]
        while prod(S) <= hosts:
            topos.append(HyperX(S))
            S[L - 1] += 1
            # If we have too many switches, increase value at the
            # appriate index and reset the values for all dimensions
            # with a larger index.
            while prod(S) > hosts:
                # Find the next index to update.  Quit if there are no
                # more indices to update.
                idx = L - 2
                if idx < 0:
                    break
                while S[idx] == (S[L - 1] - 1):
                    idx -= 1
                    if idx < 0:
                        break
                if idx < 0:
                    break
                # Update the count at the index and reset all dimensions
                # with a larger index.
                S[idx] += 1
                for i in range(idx + 1, L):
                    S[i] = S[idx]
                #XXX: this is ugly code and I hate it
                if prod(S) > hosts:
                    S[L - 1] += 1

    topos.sort(lambda x, y: cmp(x.numsw, y.numsw))
    for topo in topos:
        # T = ceil(N / (prod(S_i))
        topo.T = (hosts + topo.numsw - 1) / (topo.numsw)
        # K_i = ceil((2 * bisec * T) / S_i)
        topo.K = tuple([int(math.ceil((2 * bisec * topo.T) / Si)) for Si in topo.S])
        # If the radix is satisfied, we have found the optimal topology
        topo_radix = topo.T + sum(map(lambda x: x[0] * (x[1] - 1), zip(topo.K, topo.S)))
        if topo_radix <= radix:
            #print '%s --> %d sw, %d radix' % (topo, topo.numsw, topo_radix)
            print repr(topo)
            break

class EGFT(object):
    def __init__(self, M, C, K, numsw, numtopsw, numhosts):
        if len(M) != len(C) or len(M) != len(K):
            raise ValueError('M, C, and K must be the same length!')
        self.L = len(M)
        self.M = M
        self.C = C
        self.K = K
        self.numsw = numsw
        self.numtopsw = numtopsw
        self.numhosts = numhosts
    def __str__(self):
        return '[L=%d, M=%s, C=%s, K=%s]' % \
            (self.L, str(self.M), str(self.C), str(self.K))
    def __repr__(self):
        return '(%d, %s, %s, %s)' % \
            (self.L, str(list(self.M)), str(list(self.C)), str(list(self.K)))

    @classmethod
    def fromtuple(cls, M, C, K):
        if len(M) != len(C) or len(M) != len(K):
            raise ValueError('M, C, and K must be the same length!')
        L = len(M)
        numsw = sum([prod(M[i+1:]) * prod(C[:i+1]) for i in range(L)])
        numtopsw = prod(C)
        numhosts = prod(M)
        return cls(M, C, K, numsw, numtopsw, numhosts)

    @classmethod
    def fromegft(cls, egft, mi, ci, ki):
        M = list(egft.M)
        M.append(mi)
        C = list(egft.C)
        C.append(ci)
        K = list(egft.K)
        K.append(ki)
        numtopsw = egft.numtopsw * ci
        numsw = numtopsw + (egft.numsw * mi)
        numhosts = egft.numhosts * mi
        return cls(M, C, K, numsw, numtopsw, numhosts)

def egft_opt(args):
    c1 = 1 # Each host connects to one switch
    k1 = 1 # With only a single link

    best_egft = None
    # At least half of the lowest switches port should be hosts
    #  because we do not need Bisec > 1.0
    for m1 in range(args.radix/2, args.radix+1):
        topo = EGFT.fromtuple([m1], [c1], [k1])
        #print topo, topo.numsw
        topo = egft_recurse(args, topo, best_egft)
        if topo != None and (best_egft == None or topo.numsw < \
                best_egft.numsw):
            best_egft = topo

    if best_egft != None:
        #print '%s --> %d switches' % (str(best_egft), best_egft.numsw)
        print repr(topo)

    # Print out sanity check information for the best topology
"""
    print 'Numhosts: %d' % prod(best_egft.M)
    for i in range(best_egft.L-1):
        print 'Level %d radix: %d' % (i+1, best_egft.M[i]*best_egft.K[i] + \
                best_egft.C[i+1]*best_egft.K[i+1])
    print 'Level %d radix: %d' % (best_egft.L, \
            best_egft.M[best_egft.L-1] * best_egft.K[best_egft.L-1])
    for i in range(best_egft.L):
        print 'Level %d bisec: %f' % (i+1, 1.0 * prod(best_egft.C[:i+1]) * \
                best_egft.K[i] / prod(best_egft.M[:i]))
"""

def egft_recurse(args, topo, best_egft):
    # Optimization: quit early if the best solution is better
    if best_egft != None and topo.numsw > best_egft.numsw:
        return best_egft

    # Recursive base case
    if topo.numhosts >= args.numhosts:
        return topo

    old_mi_ki = topo.M[topo.L-1]*topo.K[topo.L-1]
    min_ci_ki = int(math.ceil(args.bisec * topo.numhosts / topo.numtopsw))
    max_ci_ki = min(old_mi_ki, args.radix - old_mi_ki)

    # Optimization: quit if the radix and bisection BW cannot be respected
    if max_ci_ki < min_ci_ki:
        return best_egft

    min_mi = 2
    max_mi = args.radix

    # Optimization (H3): If all the hosts fit at this level, choose the max m_l
    rem_modules = (args.numhosts + topo.numhosts - 1) / topo.numhosts
    if rem_modules < args.radix:
        min_mi = rem_modules
        max_mi = rem_modules

    for mi in range(min_mi, max_mi + 1):
        for ci_ki in range(min_ci_ki, max_ci_ki + 1):
            # Build all possible values for ki given ci*ki
            ci_ki_factors = factorize.primefactors(ci_ki)
            ki_vals = set()
            for r in range(len(ci_ki_factors) + 1):
                for combo in itertools.combinations(ci_ki_factors, r):
                    new_ki = prod(combo)
                    # Respect the new level's radix
                    if (new_ki * mi) <= args.radix:
                        ki_vals.add(new_ki)
            # Iterate over all possible values of ki (which determines ci)
            for ki in ki_vals:
                ci = ci_ki / ki

                # Build the new topology and recurse
                new_topo = EGFT.fromegft(topo, mi, ci, ki)
                best_egft = egft_recurse(args, new_topo, best_egft)

    return best_egft

def jellyfish_opt(args):
    assert(args.bisec >= 0 and args.bisec <= 1)
    B = args.bisec
    ln2 = math.log(2)
    k = args.radix

    # Magic from wolfram
    r = 2.0 * (2*B*B*k + math.sqrt(4*B*B*k*ln2 + 2*B*k*ln2 + ln2*ln2) + B*k + ln2) / (4*B*B + 4*B + 1)
    r = round(r)
    N = math.ceil(1.0 * args.numhosts / (k - r))

    print '-N %d -k %d -r %d' % (N, k, r)

def main():
    # Create the parser
    parser = argparse.ArgumentParser(
        description='Find an optimal topology')
    subparsers = parser.add_subparsers()

    # The number of hosts in the topology
    parser.add_argument('-n', '--numhosts', type=int, required=True, \
        help='The number of hosts in the topology')

    # The minimum bisection bandwidth of the network
    parser.add_argument('-b', '--bisec', type=float, required=True, \
        help='The minimum bisection bandwidth of the topology')

    # The maximum switch radix
    parser.add_argument('-r', '--radix', type=int, required=True, \
        help='The maximum switch radix of the topology')

    # Create a subparser for the EGFT topology
    parser_egft = subparsers.add_parser('egft', help='Extended \
    Generalized Fat Tree topology.  Described by a 4-tuple (L, M, C, K), \
    where each non-leaf node in level i has m_i child nodes with k_i \
    wide links and each non-root node has c_{i+1} parents nodes with \
    k_{i+1} wide links')
    parser_egft.set_defaults(func=egft_opt)

    # Create a subparser for the HyperX topology
    parser_hyperx = subparsers.add_parser('hyperx', help='HyperX \
    topology.  A HyperX topology is a multi-dimensional network (graph) \
    where, in each dimension, the switches are fully connected.  Every \
    switch (vertex) is a point in an L-dimensional integer lattic.  Each \
    switch is identified by a multi-index I = (I_1, ..., I_L) where 0 <= \
    I_k < S_k for each k = 1..L, where S_k is the number of switches in \
    each dimension.  A switch connects to all others whose multi-index \
    is the same in all but one coordinate.')
    parser_hyperx.set_defaults(func=hyperx_opt)

    # Crease a subparser for the Jellyfish topology
    parser_jellyfish = subparsers.add_parser('jellyfish',
        help='Jellyfish topology. A RRG(N, k, r), where each of the N \
        switches has k ports, r of which connect to other switches. \
        Bisection bandwidth is min((r/2 - sqrt(r*ln(2)))/(k - r), 1).')
    parser_jellyfish.set_defaults(func=jellyfish_opt)

    # Parse the arguments
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
