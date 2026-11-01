#!/usr/bin/env python3
"""fmask.py <cand fn.bin> [--min N] [--lo X --hi Y]: fully masked (regs, frame offsets, jump offsets, call/lddw imms) difflib
of orig vs cand; lists ours-only and orig-only runs with offsets, region labels and disassembly. Experiment only."""
import sys,os,struct,difflib
T=os.path.expanduser('~/.cache/pumpfun-reconstruction/lanes/w16a17-cto-stitch16/tools'); sys.path.insert(0,T)
from oracle import orig_window
import bdis, region
def parse(raw):
    ins=[];i=0
    while i<len(raw):
        n=16 if raw[i]==0x18 else 8; ins.append((i,bytes(raw[i:i+n]))); i+=n
    return ins
def fm(b):
    op=b[0]; cl=op&7; bb=bytearray(b)
    if op==0x18: bb[1]=0; bb[4:8]=b'\0'*4; bb[12:16]=b'\0'*4; return bytes(bb)
    if op==0x85: bb[1]=0; bb[4:8]=b'\0'*4; return bytes(bb)
    dst=b[1]&15; src=b[1]>>4
    if cl in (1,2,3):
        base=src if cl==1 else dst
        if base==10: bb[2:4]=b'\0\0'
    if cl in (5,6) and op not in (0x85,0x95): bb[2:4]=b'\0\0'
    bb[1]=0
    return bytes(bb)
def run(cand,mn=1,lo=0,hi=1<<30,show=True):
    O=parse(orig_window()); Cd=parse(open(cand,'rb').read())
    od={o:t for o,t in bdis.dis(orig_window())}; cd={o:t for o,t in bdis.dis(open(cand,'rb').read())}
    sm=difflib.SequenceMatcher(None,[fm(b) for _,b in O],[fm(b) for _,b in Cd],autojunk=False)
    M=sum(x.size for x in sm.get_matching_blocks())
    print('fully-masked M',M,'orig',len(O),'cand',len(Cd))
    for t,i1,i2,j1,j2 in sm.get_opcodes():
        if t=='equal': continue
        n=max(i2-i1,j2-j1)
        co=Cd[j1][0] if j1<len(Cd) else -1
        if n<mn or not (lo<=co<hi): continue
        oo=O[i1][0] if i1<len(O) else -1
        print(f'--- {t} orig[{oo:#x}..+{i2-i1}] cand[{co:#x}..+{j2-j1}] {region.label(co)}')
        if show:
            for k in range(max(i2-i1,j2-j1)):
                a=od[O[i1+k][0]] if i1+k<i2 else ''
                c=cd[Cd[j1+k][0]] if j1+k<j2 else ''
                ao=f'{O[i1+k][0]:#06x}' if i1+k<i2 else '      '
                cO=f'{Cd[j1+k][0]:#06x}' if j1+k<j2 else '      '
                print(f'   {ao} {a:34s} | {cO} {c}')
if __name__=='__main__':
    a=sys.argv[1:]; c=a.pop(0); mn=1; lo=0; hi=1<<30; show=True
    if '--min' in a: i=a.index('--min'); mn=int(a[i+1]); del a[i:i+2]
    if '--lo' in a: i=a.index('--lo'); lo=int(a[i+1],0); del a[i:i+2]
    if '--hi' in a: i=a.index('--hi'); hi=int(a[i+1],0); del a[i:i+2]
    if '--noshow' in a: show=False
    run(c,mn,lo,hi,show)
