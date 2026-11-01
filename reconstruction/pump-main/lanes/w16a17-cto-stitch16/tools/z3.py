#!/usr/bin/env python3
"""z3.py <cat.json> <out.jsonl>: splice-price every triple of 0 B catalogued captures with M >= 2250 on the new main
(positive-interaction search among ties). Experiment only."""
import sys,os,json,itertools
from multiprocessing import get_context
T=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,T)
import scr16,splice
items=[x for x in scr16.load_items(sys.argv[1],2250) if x['dB']==0]
V=[splice.Var(scr16.B,open(x['tpath'],'rb').read()) for x in items]
def ev(c):
    s=splice.splice(scr16.NEWB,[V[i] for i in c],scr16.B,scr16.BT)
    return None if s is None else (c,len(s),splice.M(s))
if __name__=='__main__':
    combos=list(itertools.combinations(range(len(items)),3)); print(len(items),'items',len(combos),'triples',flush=True)
    best=0
    with get_context('fork').Pool(5) as P, open(sys.argv[2],'w') as f:
        for r in P.imap_unordered(ev,combos,chunksize=16):
            if r is None: continue
            c,b,m=r; best=max(best,m)
            f.write(json.dumps({'names':[items[i]['name'] for i in c],'lanes':[items[i]['lane'] for i in c],'bytes':b,'M':m})+'\n')
            if m>=2252: print('HIT',m,b,[items[i]['name'] for i in c],flush=True)
    print('done best',best,flush=True)
