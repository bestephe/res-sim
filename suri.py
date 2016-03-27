" Copyrighted by Chad R. Meiners all rights reserved.  Contact: chad.rmeiners@gmail.com "

import math

def Intersection(left, right):
    "returns the intersection of left and right"
    if isinstance(left[0], (int, long, float, complex)): 
        low = max(left[0],right[0])
        high = min(left[1],right[1])
        return (low,high)
    else:
        return [ Intersection(left[i],right[i]) for i in xrange(len(left))]

def split(prefix):
    " Returns a pair of prefixes that cover prefix"
    size = (1 + abs(prefix[1] - prefix[0]))/2
    low = (prefix[0], prefix[0]+size-1)
    high = (prefix[0]+size, prefix[1])
    return (low, high)


#def Get_Prefixes(Interval, test = (long(0), long((2**32) - 1))):
def Get_Prefixes(Interval, test = (long(0), long((2**256) - 1))):
    " Returns the list of prefix interval inside Interval."
    i = Intersection(Interval,test)

    if (i[1]-i[0]) < 0:
        return []
    elif i == test:
        return [test]
    else:
        size = long(1 + abs(test[1] - test[0]))/2
        low = (test[0], test[0]+size-1)
        high = (test[0]+size, test[1])
        return Get_Prefixes(Interval,low) + Get_Prefixes(Interval,high)

def bin(number,size = 32):
    "return the binary string of a number padded to size"
    l = []
    while number > 0:
        number, rem = divmod(number,2)
        l.append(str(rem))

    t = "".join(l[::-1])

    return "0"* (size-len(t)) + t

def Int2Prefix(interval,size=32):
    "returns the prefix representation of the interval."
    def Prefix(br,bl):
        if len(br) == 0:
            return ''
        else:
            if br[0] == bl[0]:
                return br[0] + Prefix(br[1:],bl[1:])
            else:
                return '*'  + Prefix(br[1:],bl[1:])

    return Prefix(bin(interval[0],size), bin(interval[1],size))

def Color(Universe, At):
    " Returns a color number if contigious.  Otherwise returns False. Returns None is no rules match"
    for rule in Universe:
        
        i = Intersection(rule[0],At)
        
        if not (i[1] < i[0]):
            if (i[1] - i[0]) < (At[1] - At[0]):
                return False
            else:
                return rule[1]
        
    return None

def Weighted_Suris(Universe, Prefix, Color_Weights):
    "Returns a dictionary of all prefixes with all solution weights.   Keys are (prefix,color) = mincost."

    #len_rule = int(math.ceil(math.log(Prefix[1], 2)))
    #test = (long(0), long((2**len_rule) - 1))
    #p = Get_Prefixes(Prefix, test)

    p = Get_Prefixes(Prefix)

    Colors = Color_Weights.keys()

    # Do the right thing with no a prefix
    if len(p) == 0:
        return dict()
    elif len(p) > 1:
        r = []
        for i in [Weighted_Suris(Universe, pi, Color_Weights) for pi in p]:
            r += i.items()
        else:
            return dict(r)

    # Find the color value for Prefix
    
    c = Color(Universe,Prefix)

    # Let handle the atomic case

    if not (c is False):
        # Atomic case
        answer = dict()
        for color in Colors:
            if color != c:
                answer[(Prefix,color)] = Color_Weights[c] + Color_Weights[color]
            else:
                answer[(Prefix,color)] = Color_Weights[c]
    else:
        # Non-atomic case

        # Get subsolutions
        lowPrefix, highPrefix = split(Prefix)


        answer = dict(Weighted_Suris(Universe,lowPrefix, Color_Weights).items() +
                      Weighted_Suris(Universe,highPrefix, Color_Weights).items())

        # Find solutions at this level
        for color in Colors:
            #solutions = [ answer[(lowPrefix,cc)] + answer[(highPrefix,cc)] - Color_Weights[cc] if color == cc
            #              else answer[(lowPrefix,cc)] + answer[(highPrefix,cc)] - Color_Weights[cc] + Color_Weights[color]
            #              for cc in Colors ]
            solutions = []
            for cc in Colors:
                if color == cc:
                    sol = answer[(lowPrefix,cc)] + answer[(highPrefix,cc)] - Color_Weights[cc]
                else:
                    sol = answer[(lowPrefix,cc)] + answer[(highPrefix,cc)] - Color_Weights[cc] + Color_Weights[color]

                solutions.append(sol)

            answer[(Prefix,color)] = min(solutions)
        

    return answer

def Merge_Lists(ls1, ls2, prefix, bck_color):
    "Creates a cross product of solutions from a list of comparible sub-solutions."
    r = []
    for i in ls1:
        for j in ls2:
            assert i[-1][1] == j[-1][1]
            
            if i[-1][1] == bck_color:
                r.append(i[:-1] + j[:-1] + [(prefix, bck_color)])
            else:
                r.append(i[:-1] + j[:-1] + [(prefix,i[-1][1])] + [(prefix, bck_color)])
                        
    else:
        return r

def Find_Solutions(Universe, Prefix, Color_Weights, Answers):
    "Returns a dictionary of all minimal sub-solutions.   Keys are (prefix,color) = list of subsolution(which is a list)."

    p = Get_Prefixes(Prefix)

    Colors = Color_Weights.keys()

    # Do the right thing with no a prefix
    if len(p) == 0:
        return dict()
    elif len(p) > 1:
        r = []
        for i in [Find_Solutions(Universe, pi, Color_Weights,Answers) for pi in p]:
            r += i.items()
        else:
            return dict(r)

    # Find the color value for Prefix
    
    c = Color(Universe,Prefix)

    # Let handle the atomic case

    if not (c is False):
        # Atomic case
        answer = dict()
        for color in Colors:
            if color != c:
                answer[(Prefix,color)] = [ [ (Prefix,c), (Prefix,color) ] ]
            else:
                answer[(Prefix,color)] = [ [ (Prefix,color) ] ]
    else:
        # Non-atomic case

        # Get subsolutions
        lowPrefix, highPrefix = split(Prefix)

        answer = dict(Find_Solutions(Universe,lowPrefix, Color_Weights, Answers).items() +
                      Find_Solutions(Universe,highPrefix, Color_Weights, Answers).items())

        # Find solutions at this level
        for color in Colors:
            solutions = [ Answers[(lowPrefix,cc)] + Answers[(highPrefix,cc)] - Color_Weights[cc] if color == cc
                          else Answers[(lowPrefix,cc)] + Answers[(highPrefix,cc)] - Color_Weights[cc] + Color_Weights[color]
                          for cc in Colors ]
            goal = min(solutions)

            answer[(Prefix,color)] =  [ f  for y in [ Merge_Lists(answer[(lowPrefix,Colors[i])], answer[(highPrefix,Colors[i])], p, color)
                                        for i in range(len(Colors)) if solutions[i] == goal ] for f in y ]
        

    return answer
    

#test = [ ((0,0),1), ((0,3),0) ]
#testWeights = {1 : 1, 0: 1}

test = [ ((8,11),1), ((0,7),0), ((12,15),0) ]
testWeights = {0:1, 1:1}
prefix = (0, 15)

test = [ ((8,8),'v2'), ((10,11),'v2'), ((0,7),'v3'), ((9,9),'v3'), ((12, 15),'v3') ]
testWeights = {'v2':2, 'v3':1}

#Usage:
#x = Weighted_Suris(test,prefix,testWeights)
#print x
#y = Find_Solutions(test,prefix,testWeights,x)
#print y
#for sol in y:
#    print '    ', sol, y[sol]
