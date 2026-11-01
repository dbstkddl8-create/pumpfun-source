#!/usr/bin/env python3
"""del2.py <fn.bin> <delmap.json> [K]: M after deleting two 8-byte instructions, over pairs of the K best single
deletions (jumps re-fixed). Upper bound of a 'perfect' -16 B repay. Experiment only."""
import sys,os,json,struct,itertools,difflib
from multiprocessing import get_context
T=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,T)
from oracle import mask,orig_window
raw=open(sys.argv[1],'rb').read(); dm=json.load(open(sys.argv[2])); K=int(sys.argv[3]) if len(sys.argv)>3 else 60
OT=mask(orig_window())
def parse(raw):
    ins=[];i=0
    while i<len(raw):
        n=16 if raw[i]==0x18 else 8; ins.append(bytes(raw[i:i+n])); i+=n
    return ins
def isj(b): op=b[0]; return (op&7) in (5,6) and op not in (0x85,0x95)
INS=parse(raw); SLOT=[0]
for b in INS: SLOT.append(SLOT[-1]+len(b)//8)
off2k={SLOT[k]*8:k for k in range(len(INS))}
def delete(ks):
    ks=sorted(ks); out=[]
    def shift(s): return sum(1 for k in ks if SLOT[k]<s)
    for j,b in enumerate(INS):
        if j in ks: continue
        if isj(b):
            off=struct.unpack('<h',b[2:4])[0]; t=SLOT[j]+1+off
            ns=SLOT[j]-shift(SLOT[j]+1)+1; nt=t-shift(t+1) if t not in [SLOT[k] for k in ks] else t-shift(t)
            bb=bytearray(b); bb[2:4]=struct.pack('<h',nt-ns); b=bytes(bb)
        out.append(b)
    return b''.join(out)
def M(c): return sum(x.size for x in difflib.SequenceMatcher(None,OT,mask(c),autojunk=False).get_matching_blocks())
def ev(c): return (c,M(delete([off2k[o] for o in c])))
if __name__=='__main__':
    top=[o for o,m in dm['res'][:K]]
    combos=list(itertools.combinations(top,2))
    with get_context('fork').Pool(4) as P: res=P.map(ev,combos,chunksize=8)
    res.sort(key=lambda z:-z[1])
    print('pairs',len(res),'top',[(hex(a),hex(b),m) for (a,b),m in res[:15]])
    json.dump([[a,b,m] for (a,b),m in res],open(sys.argv[2].replace('.json','_pairs.json'),'w'))
