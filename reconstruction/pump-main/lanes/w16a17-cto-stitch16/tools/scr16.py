#!/usr/bin/env python3
"""scr16.py: splice-oracle screens on the CURRENT main (599891304; base = this lane's rx/main/fn.bin) over the cat16
catalog (old-source captures already translated onto A6+ev6). Experiment only; predictions, not builds.
  scr16.py pairs   <cat.json> <out.jsonl> [--min-m 2200] [--np 6]          every conflict-free zero-sum pair
  scr16.py triples <cat.json> <out.jsonl> [--min-dm -10] [--max-abs 256]   zero-sum triples of small items
  scr16.py lead    <cat.json> <lead.bin> <out.jsonl> [--pairs] [--triples]  lead + 1/2/3 items to reach 27,400 B
Items: source captures (not RA/frame/relayout/permutation oracles), translatable onto the new main, M >= --min-m,
deduplicated by translated bytes, main-identical ones dropped."""
import sys,os,json,re,itertools,hashlib
from multiprocessing import Pool,get_context
T=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,T)
import splice
ME=os.path.dirname(T)
NEWB=open(ME+'/rx/main/fn.bin','rb').read(); B=splice.parse(NEWB); BT=splice.targets(B)
NONSRC=re.compile(r'(ra$|Br$|TB$|^mpp_|^mp_|^jt_|^spl_|__r|p2|perm|^fs_|^B$)')
def arg(a,k,d,f=str):
    if k in a: i=a.index(k); v=f(a[i+1]); del a[i:i+2]; return v
    return d
def load_items(cat,minm,extra=None):
    d=json.load(open(cat)); seen=set(); out=[]
    for x in d:
        if x['tM'] is None or x['nonsrc'] or NONSRC.search(x['name']) or x.get('tmh') or x.get('excluded'): continue
        if x['tM']<minm: continue
        raw=open(x['tpath'],'rb').read()
        if raw==NEWB or splice.mask(raw)==splice.mask(NEWB): continue
        h=hashlib.sha1(raw).hexdigest()
        if h in seen: continue
        seen.add(h); out.append(x)
    return out
V={}
def mkvar(p): return splice.Var(B,open(p,'rb').read())
def ev(c):
    vs=[V[i] for i in c]
    s=splice.splice(NEWB,vs,B,BT)
    if s is None: return None
    return (c,len(s),splice.M(s))
def run(items,combos,outf,np_,tag,thr=2251,lead=None):
    print(len(items),'items',len(combos),'combos',flush=True)
    n=0;best=0
    with get_context("fork").Pool(np_) as P, open(outf,'w') as f:
        for r in P.imap_unordered(ev,combos,chunksize=8):
            if r is None: continue
            c,b,m=r; n+=1
            names=[items[i]['name'] if i>=0 else 'LEAD' for i in c]
            row={'mode':tag,'names':names,'lanes':[items[i]['lane'] if i>=0 else lead for i in c],'genes':[items[i]['genes'] if i>=0 else None for i in c],
                 'deltas':[items[i]['dB'] if i>=0 else None for i in c],'Ms':[items[i]['tM'] if i>=0 else None for i in c],'bytes':b,'M':m}
            f.write(json.dumps(row)+'\n')
            if m>=thr and b==27400: print('HIT',m,b,names,flush=True)
            best=max(best,m if b==27400 else 0)
    print('done',n,'priced; best at 27400:',best,flush=True)
if __name__=='__main__':
    a=sys.argv[1:]; mode=a.pop(0)
    minm=arg(a,'--min-m',2200,int); np_=arg(a,'--np',6,int); mindm=arg(a,'--min-dm',-10,int); maxabs=arg(a,'--max-abs',256,int)
    pairs='--pairs' in a; tri='--triples' in a; a=[x for x in a if x not in ('--pairs','--triples')]
    items=load_items(a[0],minm)
    paths=[x['tpath'] for x in items]
    with Pool(np_) as P: vs=P.map(mkvar,paths,chunksize=4)
    for i,v in enumerate(vs): V[i]=v
    n=len(items); dB=[x['dB'] for x in items]; dM=[x['dM'] for x in items]
    if mode=='pairs':
        combos=[(i,j) for i,j in itertools.combinations(range(n),2) if dB[i]+dB[j]==0 and not (dB[i]==0 and dM[i]+dM[j]<-6)]
        run(items,combos,a[1],np_,'pairs')
    elif mode=='triples':
        sm=[i for i in range(n) if abs(dB[i])<=maxabs and dM[i]>=mindm]
        combos=[c for c in itertools.combinations(sm,3) if sum(dB[i] for i in c)==0 and not all(dB[i]==0 for i in c)]
        print('small items',len(sm),flush=True)
        run(items,combos,a[1],np_,'triples')
    elif mode=='lead':
        lead=a[0+1]; outf=a[2]; L=open(lead,'rb').read(); V[-1]=splice.Var(B,L); need=27400-len(L)
        combos=[(-1,i) for i in range(n) if dB[i]==need]
        if pairs: combos+=[(-1,i,j) for i,j in itertools.combinations(range(n),2) if dB[i]+dB[j]==need and dM[i]+dM[j]>=mindm*2]
        if tri:
            sm=[i for i in range(n) if abs(dB[i])<=maxabs and dM[i]>=mindm]
            combos+=[(-1,)+c for c in itertools.combinations(sm,3) if sum(dB[i] for i in c)==need]
        print('lead',lead,'bytes',len(L),'M',splice.M(L),'need',need,flush=True)
        run(items,combos,outf,np_,'lead:'+os.path.basename(lead),lead=lead)
