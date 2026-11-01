#!/usr/bin/env python3
"""slotbound.py <fn.bin> <n_del> [lo_hex hi_hex]: delete n_del 8-byte non-jump instructions that are UNMATCHED in the
difflib alignment against the original (so M is kept up to jump-displacement effects), chosen greedily inside
[lo,hi) (candidate offsets), jumps re-fixed; report M and positional slots_diff. Bound for a size repay placed in a
region. Experiment only."""
import sys,os,struct,difflib
T=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,T)
from oracle import mask,orig_window,metric
O=orig_window(); OT=mask(O)
raw=open(sys.argv[1],'rb').read(); n=int(sys.argv[2]); lo=int(sys.argv[3],16) if len(sys.argv)>3 else 0; hi=int(sys.argv[4],16) if len(sys.argv)>4 else 1<<30
def parse(raw):
    ins=[];i=0
    while i<len(raw):
        k=16 if raw[i]==0x18 else 8; ins.append(bytes(raw[i:i+k])); i+=k
    return ins
def isj(b): op=b[0]; return (op&7) in (5,6) and op not in (0x85,0x95)
def delete(INS,ks):
    SLOT=[0]
    for b in INS: SLOT.append(SLOT[-1]+len(b)//8)
    ks=set(ks); out=[]
    dels=sorted(SLOT[k] for k in ks)
    import bisect
    def sh(s): return bisect.bisect_left(dels,s)
    for j,b in enumerate(INS):
        if j in ks: continue
        if isj(b):
            off=struct.unpack('<h',b[2:4])[0]; t=SLOT[j]+1+off
            ns=SLOT[j]-sh(SLOT[j])+1; nt=t-sh(t)
            bb=bytearray(b); bb[2:4]=struct.pack('<h',nt-ns); b=bytes(bb)
        out.append(b)
    return b''.join(out)
INS=parse(raw); SLOT=[0]
for b in INS: SLOT.append(SLOT[-1]+len(b)//8)
CT=mask(raw)
sm=difflib.SequenceMatcher(None,OT,CT,autojunk=False); matched=set()
for bl in sm.get_matching_blocks():
    for k in range(bl.size): matched.add(bl.b+k)
cands=[k for k in range(len(INS)) if k not in matched and len(INS[k])==8 and not isj(INS[k]) and INS[k][0] not in (0x85,0x95) and lo<=SLOT[k]*8<hi]
# greedy: take unmatched candidates from the END of the range backwards (repay placed late)
ks=cands[-n:] if n<=len(cands) else cands
s=delete(INS,ks)
r,sd=metric(s,O)
M=sum(b.size for b in difflib.SequenceMatcher(None,OT,mask(s),autojunk=False).get_matching_blocks())
print({'bytes':len(s),'M':M,'slots':sd,'deleted_at':[hex(SLOT[k]*8) for k in ks]})
