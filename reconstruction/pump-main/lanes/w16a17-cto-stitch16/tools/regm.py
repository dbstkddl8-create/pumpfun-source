#!/usr/bin/env python3
"""regm.py <fn.bin>...: per orig-region matched tokens under masks: exact (scorer mask), r (regs masked), f (frame masked),
rf (both), rfj (+jumps). Experiment only."""
import sys,os,difflib
sys.path.insert(0,os.path.expanduser('~/.cache/pumpfun-reconstruction/lanes/w16a17-cto-stitch16/tools'))
from oracle import orig_window, mask
OREG=[(0x0,'E'),(0x3a8,'V'),(0x1a88,'SH'),(0x26b8,'TC'),(0x3c40,'SC'),(0x4a28,'PC'),(0x5490,'ER'),(0x5990,'NA'),(0x5bc0,'WA'),(0x6a68,'TL')]
def lab(o):
    r='E'
    for a,n in OREG:
        if o>=a: r=n
    return r
def parse(raw):
    ins=[];i=0
    while i<len(raw):
        n=16 if raw[i]==0x18 else 8; ins.append((i,bytes(raw[i:i+n]))); i+=n
    return ins
def mk(b,r,f,j):
    op=b[0]; cl=op&7; bb=bytearray(b)
    if op==0x18: bb[4:8]=b'\0'*4; bb[12:16]=b'\0'*4
    if op==0x85: bb[1]&=0x0f; bb[4:8]=b'\0'*4
    if f and cl in (1,2,3) and ((b[1]>>4) if cl==1 else (b[1]&15))==10: bb[2:4]=b'\0\0'
    if j and cl in (5,6) and op not in (0x85,0x95): bb[2:4]=b'\0\0'
    if r: bb[1]=0 if not (cl in (1,2,3) and ((b[1]>>4) if cl==1 else (b[1]&15))==10) else (b[1]&0xf0 if cl==1 else b[1]&0x0f)
    return bytes(bb)
O=parse(orig_window())
def run(p,modes=(('ex',0,0,0),('r',1,0,0),('f',0,1,0),('rf',1,1,0),('rfj',1,1,1))):
    C=parse(open(p,'rb').read()); res={}
    for nm,r,f,j in modes:
        if nm=='ex':
            a=mask(orig_window()); c=mask(open(p,'rb').read())
            # mask() returns token list aligned with parse order
            sm=difflib.SequenceMatcher(None,a,c,autojunk=False)
        else:
            sm=difflib.SequenceMatcher(None,[mk(b,r,f,j) for _,b in O],[mk(b,r,f,j) for _,b in C],autojunk=False)
        per={}
        for i,jj,n in sm.get_matching_blocks():
            for k in range(n): per[lab(O[i+k][0])]=per.get(lab(O[i+k][0]),0)+1
        per['all']=sum(per.values()); res[nm]=per
    return len(open(p,'rb').read()),res
if __name__=='__main__':
    names=[n for _,n in OREG]+['all']
    rows={}
    for p in sys.argv[1:]:
        L,res=run(p); rows[p]=res
        print(p.split('/')[-2],L)
        for m,per in res.items(): print(f'  {m:4s}',' '.join(f'{n}:{per.get(n,0):4d}' for n in names))
