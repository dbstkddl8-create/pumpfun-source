#!/usr/bin/env python3
"""skel.py <catalog.json> <out.json> [--np N]: skeleton leaderboard. For every usable capture (translated onto the current
main: tpath), per orig-region matched tokens exact (scorer mask) and rfj (regs, frame offsets, jump offsets masked),
so shim lanes can pick the base with the best skeleton. Experiment only."""
import sys,os,json
from multiprocessing import get_context
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import regm
def ev(r):
    try:
        L,res=regm.run(r['tpath'],modes=(('ex',0,0,0),('rfj',1,1,1)))
        return {'lane':r['lane'],'name':r['name'],'tpath':r['tpath'],'bytes':L,'base':r.get('base'),'genes':r.get('genes'),'res':res}
    except Exception as e: return None
if __name__=='__main__':
    a=sys.argv[1:]; cat=a[0]; out=a[1]; NP=4
    if '--np' in a: NP=int(a[a.index('--np')+1])
    rows=[r for r in json.load(open(cat)) if r.get('tpath') and not r.get('nonsrc') and not r.get('tmh') and not r.get('excluded') and (r.get('tM') or 0)>=0]
    print('rows',len(rows),flush=True)
    with get_context('fork').Pool(NP) as p: R=[x for x in p.map(ev,rows,chunksize=4) if x]
    R.sort(key=lambda x:-x['res']['rfj']['all'])
    json.dump(R,open(out,'w'))
    print('done',len(R))
