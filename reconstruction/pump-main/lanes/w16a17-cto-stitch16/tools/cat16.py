#!/usr/bin/env python3
"""cat16.py <out.json> [NP] [--lanes GLOB...]: universal admin_cto capture catalog on the CURRENT main (599891304 =
1f4e396 admin_cto source: ev6+A6). Experiment only.
For every cached raw-IR capture (rx/*/fn.bin) of the w15/w16 lanes: bytes, exact M, the size of its instruction diff
against the old main (9bd38c7 source) and the new main, and its base (the nearer one). Captures on the old source are
translated to the new main with the splice oracle: splice(old main, [new main, X]) (= X's local change applied on top of
A6+ev6); a conflict means X touches the A6/ev6 hunks and needs a recapture. Provenance (genes) comes from the lane's
res*.jsonl / res.txt rows when present, else from the ledger (hypothesis). Non-source captures (RA forces, spill
permutations, IR edits) are flagged by name and gene text."""
import sys,os,json,glob,hashlib,difflib,re
from multiprocessing import Pool
T=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,T)
import splice
from oracle import mask
C=os.path.expanduser('~/.cache/pumpfun-reconstruction/lanes')
ME=C+'/w16a17-cto-stitch16'
NEW=open(ME+'/rx/main/fn.bin','rb').read(); OLD=open(ME+'/rx/main9bd/fn.bin','rb').read()
NB=splice.parse(NEW); OB=splice.parse(OLD); NBT=splice.targets(NB); OBT=splice.targets(OB)
NN=[splice.norm(x) for x in NB]; ON=[splice.norm(x) for x in OB]
NEWV=None
TX=ME+'/tx'
NONSRC=re.compile(r'(__ra|__r$|__r_|p2__|^mp_|perm|_ra$|^ra_|^fs_|force|relab|^ir_|^IR)',re.I)
NONSRC2=re.compile(r'(ra$|Br$|TB$|^mpp_|^mp_|^jt_|^spl_|^B$)')
def nonsrc(name,g):
    g2=g.replace('raw-IR','raw_ir').replace('raw IR','raw_ir')
    return bool(NONSRC.search(name) or NONSRC2.search(name) or re.search(r'(^|[\s(;:])IR\b|IR edit|IR-edit|IR-only|post-opt|RA force|RA-force|oracle bound|spill perm|relabel|relayout|ceiling build',g2))
def ndiff(a,b):
    sm=difflib.SequenceMatcher(None,a,b,autojunk=False); n=0
    for t,i1,i2,j1,j2 in sm.get_opcodes():
        if t!='equal': n+=max(i2-i1,j2-j1)
    return n
def prov_rows():
    P={}
    for f in glob.glob(C+'/w1[56]*/res*.jsonl')+glob.glob(C+'/w1[56]*/data/res*.jsonl'):
        lane=f[len(C)+1:].split('/')[0]
        for l in open(f):
            try: r=json.loads(l)
            except Exception: continue
            if not isinstance(r,dict) or 'name' not in r or 'error' in r: continue
            P.setdefault((lane,r['name']),{'genes':r.get('genes'),'src':os.path.basename(f),'M':r.get('M'),'bytes':r.get('bytes')})
    f=C+'/w15a13-cto-jointraceback/res.txt'
    if os.path.exists(f):
        for l in open(f):
            n=l.split('|')[0].strip()
            if n: P.setdefault(('w15a13-cto-jointraceback',n),{'genes':'e/'+n.split('_')[0]+'.py'+(' (+ knob '+'_'.join(n.split('_')[1:])+')' if '_' in n else ''),'src':'res.txt'})
    return P
def ledger_rows():
    L=os.path.expanduser('~/.cache/pumpfun-reconstruction/pump-main/ATTEMPTS.jsonl'); R={}
    for l in open(L):
        if '0x22a10' not in l or ('w15' not in l and 'w16' not in l): continue
        try: d=json.loads(l)
        except Exception: continue
        k=d.get('dedupe_key','')
        m=re.match(r'0x22a10-w1[56]-\w+-[\w]+?-(.+)-v\d+$',k)
        nm=None
        o=str((d.get('data') or {}).get('output','') if isinstance(d.get('data'),dict) else '')
        mo=re.search(r'/rx/([^/]+)/?$',o)
        if mo: nm=mo.group(1)
        elif m: nm=m.group(1)
        if nm: R[(d.get('lane',''),nm)]=str(d.get('hypothesis',''))[:300]
    return R
def ev(p):
    raw=open(p,'rb').read()
    if not (26000<=len(raw)<=29000): return None
    lane=p[len(C)+1:].split('/')[0]; name=p.split('/')[-2]
    toks=splice.parse(raw); nt=[splice.norm(x) for x in toks]
    dn=ndiff(NN,nt); do=ndiff(ON,nt)
    M=splice.M(raw)
    d={'lane':lane,'name':name,'path':p,'bytes':len(raw),'M':M,'d_new':dn,'d_old':do}
    if dn<=do:
        d['base']='new'; d['tbytes']=len(raw); d['tM']=M; d['tpath']=p
    else:
        d['base']='old'
        global NEWV
        if NEWV is None: NEWV=splice.Var(OB,NEW)
        try: s=splice.splice(OLD,[NEWV,raw],OB,OBT)
        except Exception as e: s=None
        if s is None: d['tbytes']=None; d['tM']=None; d['tpath']=None
        else:
            h=hashlib.sha1(raw).hexdigest()[:12]; tp=f'{TX}/{lane}__{name}__{h}.bin'
            open(tp,'wb').write(s); d['tbytes']=len(s); d['tM']=splice.M(s); d['tpath']=tp
    return d
if __name__=='__main__':
    a=sys.argv[1:]; out=a[0]; NP=int(a[1]) if len(a)>1 and a[1].isdigit() else 6
    os.makedirs(TX,exist_ok=True)
    pats=[x for x in a[2:] if not x.isdigit()] or [C+'/w15*/rx/*/fn.bin',C+'/w16*/rx/*/fn.bin']
    paths=[]
    for g in pats: paths+=sorted(glob.glob(g))
    seen={}; uniq=[]; dup={}
    for p in paths:
        if '/w16a17-cto-stitch16/' in p: continue
        try: raw=open(p,'rb').read()
        except Exception: continue
        h=hashlib.sha1(raw).hexdigest()
        if h in seen: dup.setdefault(seen[h],[]).append(p); continue
        seen[h]=p; uniq.append(p)
    print('paths',len(paths),'unique',len(uniq),flush=True)
    P=prov_rows(); LR=ledger_rows()
    with Pool(NP) as pool: res=[d for d in pool.map(ev,uniq,chunksize=8) if d is not None]
    for d in res:
        k=(d['lane'],d['name']); pr=P.get(k)
        d['genes']=pr['genes'] if pr else None; d['resfile']=pr['src'] if pr else None
        d['hyp']=LR.get(k)
        g=(d['genes'] or '')+' '+(d['hyp'] or '')
        d['nonsrc']=nonsrc(d['name'],g)
        d['dups']=[x[len(C)+1:] for x in dup.get(d['path'],[])][:6]
        d['dM']=(d['tM']-2251) if d['tM'] is not None else None
        d['dB']=(d['tbytes']-27400) if d['tbytes'] is not None else None
    res.sort(key=lambda d:(-(d['tM'] or 0)))
    json.dump(res,open(out,'w'),indent=0)
    print('done',len(res),'new',sum(d['base']=='new' for d in res),'old',sum(d['base']=='old' for d in res),
          'translated',sum(d['base']=='old' and d['tM'] is not None for d in res),flush=True)
