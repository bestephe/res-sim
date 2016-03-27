#!/usr/bin/python

import copy
import suri
import sys

def CheckCrossPattern(r1, r2):
    r1wild, r2wild = False, False
    assert(len(r1) == len(r2))
    for i in range(len(r1)):
        if r1[i] == '*' and r2[i] != '*':
            r1wild = True
        elif r1[i] != '*' and r2[i] == '*':
            r2wild = True
        if r1wild and r2wild:
            return True
    return False

def FindMinPartition(table):
    L = [] # The list of partitions
    P = [] # The current partition
    for entry in reversed(table):
        rule, output = entry
        for r2, o2 in P:
            if CheckCrossPattern(rule, r2):
                P.reverse() # Maintain order
                L.append(P)
                P = [entry]
                break
        else:
            P.append(entry)
    P.reverse() # Maintain order
    L.append(P)
    L.reverse() # Maintain order
    return L

def PrefixBitSwap(table):
    n, b = len(table), len(table[0][0])
    B = []
    for i in range(b):
        starcnt = 0
        for rule, output in table:
            if rule[i] == '*':
                starcnt += 1
        B.append((i, starcnt))
    B.sort(lambda x, y: cmp(x[1], y[1]))
    M = copy.deepcopy(table)
    for k in range(b):
        i, j = B[k]
        for entry_i in range(n):
            rule, output = table[entry_i]
            M[entry_i][0][k] = rule[i]
    return M, B

def BitRecovery(table, B):
    b = len(B)
    M = copy.deepcopy(table)
    for k in range(b):
        i, j = B[k]
        for entry_i in range(len(table)):
            rule, output = table[entry_i]
            M[entry_i][0][i] = rule[k]
    return M
    
def SuriFmt(table):
    suri_table, suri_weights = [], {}
    for rule, output in table:
        numstar = rule.count('*')
        low = int(''.join(rule[:len(rule) - numstar]), 2) * (2 ** numstar)
        high = low + (2 ** numstar) - 1
        suri_table.append(((low, high), output))
        if output not in suri_weights:
            suri_weights[output] = 1

    # Add the None Rule
    rule_len = len(table[0][0])
    suri_table.append(((0, (2**rule_len) - 1), None))
    suri_weights[None] = 200000
    return suri_table, suri_weights

def SuriUnfmt(suri_sol, len_entry):
    assert(suri_sol[-1][1] == None)
    new_table = []
    for suri_rule, output in suri_sol[:-1]:
        if isinstance(suri_rule, list):
            # XXX: annoying hack to deal with odd Suri output
            assert(len(suri_rule) == 1)
            suri_rule = suri_rule[0]
        fmt_rule = suri.Int2Prefix(suri_rule, len_entry)
        new_table.append((list(fmt_rule), output))
    return new_table

def BitMask(rule):
    mask = set()
    for i, bit in enumerate(rule):
        if bit == '*':
            mask.add(i)
    return frozenset(mask)

def HammingDist(r1, r2):
    dist = set()
    for i in range(len(r1)):
        if r1[i] != r2[i]:
            dist.add(i)
    return frozenset(dist)

# Algorithm 3 from Bit Weaving
def BitMerge(table):
    # Helper Functions
    def GetPrefixLen(rule):
        try:
            return rule.index('*')
        except:
            return len(rule)
    def CmpPrefixLen(e1, e2):
        prefixcmp = cmp(GetPrefixLen(e2[0]), GetPrefixLen(e1[0]))
        if prefixcmp == 0:
            return cmp(e1[0], e2[0])
        else:
            return prefixcmp

    # Sort in decreasing order
    #prefixlens = {rule: GetPrefixLen(rule) for rule, output in table}
    S = table[:]
    S.sort(CmpPrefixLen)
    C = {} # (bitmask, output) -> list
    for rule, output in S:
        bitmask = BitMask(rule)
        if (bitmask, output) not in C:
            C[(bitmask, output)] = []
        C[(BitMask(rule), output)].append(rule)
    
    #OS = set()
    O = []
    for (bm, output), c in C.iteritems():
        if len(c) == 1:
            O.append((c[0], output))
        else:
            added = [False] * len(c)
            for i in range(len(c) - 1):
                for j in range(i+1, len(c)):
                    dist = HammingDist(c[i], c[j])
                    if len(dist) == 1:
                        added[i], added[j] = True, True
                        diff_i = dist.__iter__().next()
                        assert(c[i][diff_i] != '*')
                        assert(c[j][diff_i] != '*')
                        tcover = [c[i][bit_i] if bit_i != diff_i else '*' \
                            for bit_i in range(len(c[i]))]
                        #OS.add((tcover, output))
                        O.append((tcover, output))
            for i, flag in enumerate(added):
                if not flag:
                    O.append((c[i], output))
    #O = list(OS)
    O.sort(CmpPrefixLen)

    #print 'S:'
    #for entry in S:
    #    print '    ', entry
    #print 'O:'
    #for entry in O:
    #    print '    ', entry

    if S == O:
        return O
    else:
        return BitMerge(O)

def BitWeave(table):
    "The table is a list of 2-tuples.  Each tuple is (bits, output)"

    # Remove the 'None' rule if it exists
    if table[-1][1] == None:
        #print 'Removing None rule'
        table.pop()

    #print table
    #for entry in table:
    #    print entry

    # Find the minimal partitions
    partitions = FindMinPartition(table)

    # Assert that the order of the partitions is stable
    table_iter = table.__iter__()
    for partition in partitions:
        for entry in partition:
            assert(entry == table_iter.next())

    new_table = []
    len_rule = len(table[0][0])
    for partition in partitions:
        # No optimization possible
        if len(partition) <= 1:
            new_table += partition
            continue

        # Find a Bitswap over each partition
        bitswap_table, B = PrefixBitSwap(partition)
        
        #print 'BitSwap:'
        #for entry in bitswap_table:
        #    print '    ', entry
        #print 'len_rule: ', len_rule
        
        # Assert that BitRecovery works
        recovered_table = BitRecovery(bitswap_table, B)
        assert(recovered_table == partition)

        suri_table, suri_weights = SuriFmt(bitswap_table)
        assert(suri_table[-1][1] == None)
        tmp = suri.Weighted_Suris(suri_table, suri_table[-1][0],
            suri_weights)
        suri_sols = suri.Find_Solutions(suri_table, suri_table[-1][0],
            suri_weights, tmp)
        suri_sol = suri_sols[suri_table[-1]][0]
        try:
            minimized_table = SuriUnfmt(suri_sol, len_rule)
        except:
            print 'Suri Sol:'
            print suri_sols[suri_table[-1]]
            raise
            sys.exit(1)

        bitmerge_table = BitMerge(minimized_table)

        #if len(minimized_table) != len(bitmerge_table):
        #    print 'Minimized Table:'
        #    for entry in minimized_table:
        #        print '    ', entry
        #    print 'BitMerged Table:'
        #    for entry in bitmerge_table:
        #        print '    ', entry

        recovered_table = BitRecovery(bitmerge_table, B)
        new_table += recovered_table
    # Add in a None rule
    new_table.append((['*'] * len_rule, None))
    return new_table

#assert(CheckCrossPattern('0*', '1*') == False)
#assert(CheckCrossPattern('1*', '0*') == False)
#assert(CheckCrossPattern('0*', '*0') == True)
#assert(CheckCrossPattern('1*', '*0') == True)
#assert(CheckCrossPattern('0*', '*1') == True)
#assert(CheckCrossPattern('**', '*1') == False)
#print 'Check complete!'
