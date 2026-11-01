#!/usr/bin/env python3
"""drift.py <fn.bin>: drift profile (cand offset - orig offset) of the difflib-matched instructions (scorer mask), by orig
region; positional slot matches; experiment only."""
import sys,os,difflib,collections
sys.path.insert(0,os.path.expanduser('~/.cache/pumpfun-reconstruction/lanes/w16a17-cto-stitch16/tools'))
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from oracle import orig_window, mask
import regm
def prof(p):
    o=orig_window(); c=open(p,'rb').read()
    O=regm.parse(o); C=regm.parse(c)
    a=mask(o); b=mask(c)
    sm=difflib.SequenceMatcher(None,a,b,autojunk=False)
    D=collections.Counter(); byreg=collections.defaultdict(collections.Counter)
    for i,j,n in sm.get_matching_blocks():
        for k in range(n):
            d=C[j+k][0]-O[i+k][0]; D[d]+=1; byreg[regm.lab(O[i+k][0])][d]+=1
    # positional slot matches (8-byte slots, compare masked bytes at same offset)
    pos=0
    for x in range(0,min(len(o),len(c)),8):
        if o[x:x+8]==c[x:x+8]: pos+=1
    return D,byreg,pos,len(c)
if __name__=='__main__':
    for p in sys.argv[1:]:
        D,byreg,pos,L=prof(p)
        print(p.split('/')[-2],L,'M',sum(D.values()),'drift0',D.get(0,0),'raw-equal 8B slots',pos)
        print('  top drifts',D.most_common(8))
        for r in [n for _,n in regm.OREG]:
            if r in byreg: print('   ',r,byreg[r].most_common(4))
