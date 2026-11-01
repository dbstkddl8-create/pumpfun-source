#!/usr/bin/env python3
"""cat16b.py <out.json> [--prev <old catalog>] [--np N]: cat16 v2, the universal admin_cto capture catalog on the CURRENT
main (599891304 = 1f4e396 admin_cto source: A6 + ev6), with every correction of round 1 built in. Experiment only.
- Walks every w15*/w16* rx/*/fn.bin (26-29 KB), dedupes by bytes (a source-named duplicate wins over mp_/__ra/... names).
- Base: the lane's res-<sha7>.jsonl file, else the ledger key's main sha7, else the nearer main by instruction-diff size.
  Old source = 9bd38c7/86e2a6b/9120883/1cc4879; new = 1f4e396/5998913/7e5ba44; anything older is excluded.
- Old-source captures are translated with splice(old main, [new main, X]); a capture whose own diff touches the A6/ev6
  hunks (old-main tokens 1115-1133, 2425-2495) is flagged tmh. Guessed-new captures that sit as close to the old main are
  tmh-checked too (an old capture holding one of main's two hunks looks "new").
- Every usable capture is snapshotted into $OUT/tx (other lanes overwrite or delete their rx dirs).
- --prev reuses the expensive per-capture fields (M, diffs, translation) by sha1."""
import sys,os,json,glob,hashlib,difflib,re
from multiprocessing import get_context
T=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,T)
import splice
C=os.path.expanduser('~/.cache/pumpfun-reconstruction/lanes')
ME=C+'/w16a17-cto-stitch16'; TX=ME+'/tx'
NEW=open(ME+'/rx/main/fn.bin','rb').read(); OLD=open(ME+'/rx/main9bd/fn.bin','rb').read()
NB=splice.parse(NEW); OB=splice.parse(OLD); OBT=splice.targets(OB)
NN=[splice.norm(x) for x in NB]; ON=[splice.norm(x) for x in OB]
NEWV=splice.Var(OB,NEW)
OLDS={'9bd38c7','86e2a6b','9120883','1cc4879'}; NEWS={'1f4e396','5998913','7e5ba44','1647da0'}
TMH=[(1115,1133),(2425,2495)]
NONSRC=re.compile(r'(__ra|__r$|__r_|p2__|^mp_|perm|_ra$|^ra_|^fs_|force|relab|^ir_|^IR|ra$|Br$|TB$|^mpp_|^jt_|^spl_|^B$)')
def nonsrc(name,g):
    g2=(g or '').replace('raw-IR','raw_ir').replace('raw IR','raw_ir')
    return bool(NONSRC.search(name) or re.search(r'(^|[\s(;:])IR\b|IR edit|IR-edit|IR-only|post-opt|RA force|RA-force|oracle bound|spill perm|relabel|relayout|ceiling build',g2))
def ops(a,b): return difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes()
def ndiff(o): return sum(max(i2-i1,j2-j1) for t,i1,i2,j1,j2 in o if t!='equal')
def tmh_of(o): return any(t!='equal' and i1<=hi and i2>=lo for t,i1,i2,j1,j2 in o for lo,hi in TMH)
def translate(raw):
    s=splice.splice(OLD,[NEWV,raw],OB,OBT)
    return s
def ev(p):
    raw=open(p,'rb').read(); nt=[splice.norm(x) for x in splice.parse(raw)]
    on=ops(NN,nt); oo=ops(ON,nt)
    d={'M':splice.M(raw),'bytes':len(raw),'d_new':ndiff(on),'d_old':ndiff(oo),'tmh_old':tmh_of(oo)}
    s=translate(raw)
    d['tr_bytes']=None if s is None else len(s); d['tr_M']=None if s is None else splice.M(s)
    return p,d
def prov():
    P={}
    for f in glob.glob(C+'/w1[5-7]*/res*.jsonl')+glob.glob(C+'/w1[5-7]*/data/res*.jsonl'):
        lane=f[len(C)+1:].split('/')[0]; m=re.search(r'res-([0-9a-f]{7})',os.path.basename(f))
        for l in open(f):
            try: r=json.loads(l)
            except Exception: continue
            if isinstance(r,dict) and 'name' in r and 'error' not in r:
                P.setdefault((lane,r['name']),{'genes':r.get('genes'),'src':os.path.basename(f),'sha':m.group(1) if m else None})
    f=C+'/w15a13-cto-jointraceback/res.txt'
    if os.path.exists(f):
        for l in open(f):
            n=l.split('|')[0].strip()
            if n: P.setdefault(('w15a13-cto-jointraceback',n),{'genes':'e/'+n+'.py','src':'res.txt','sha':None})
    return P
def ledger():
    L=os.path.expanduser('~/.cache/pumpfun-reconstruction/pump-main/ATTEMPTS.jsonl'); R={}
    for l in open(L):
        if '0x22a10' not in l or ('w15' not in l and 'w16' not in l and 'w17' not in l): continue
        try: d=json.loads(l)
        except Exception: continue
        k=d.get('dedupe_key',''); m=re.match(r'0x22a10-w1[5-7]-([0-9a-f]{7})-',k)
        dd=d.get('data') if isinstance(d.get('data'),dict) else {}
        mo=re.search(r'/rx/([^/]+)/?$',str(dd.get('output','')))
        m2=re.match(r'0x22a10-w1[5-7]-\w+-[\w]+?-(.+)-v\d+$',k)
        nm=mo.group(1) if mo else (m2.group(1) if m2 else None)
        if nm: R[(d.get('lane',''),nm)]={'hyp':str(d.get('hypothesis',''))[:300],'sha':m.group(1) if m else None}
    return R
if __name__=='__main__':
    a=sys.argv[1:]; out=a.pop(0); prev={}; NP=5
    if '--prev' in a:
        i=a.index('--prev');
        for x in json.load(open(a[i+1])):
            if x.get('sha1') and x.get('ev'): prev[x['sha1']]=x['ev']
        del a[i:i+2]
    if '--np' in a: i=a.index('--np'); NP=int(a[i+1]); del a[i:i+2]
    os.makedirs(TX,exist_ok=True)
    paths=sorted(glob.glob(C+'/w15*/rx/*/fn.bin')+glob.glob(C+'/w16*/rx/*/fn.bin')+glob.glob(C+'/w17*/rx/*/fn.bin')+glob.glob(C+'/w17*/rx/*/*/fn.bin'))
    groups={}
    for p in paths:
        if '/w16a17-cto-stitch16/' in p: continue
        try: raw=open(p,'rb').read()
        except Exception: continue
        if not (26000<=len(raw)<=29000): continue
        groups.setdefault(hashlib.sha1(raw).hexdigest(),[]).append(p)
    P=prov(); LR=ledger()
    def nm(p): return p[len(C)+1:].split('/')[0],p.split('/')[-2]
    todo=[ps[0] for h,ps in groups.items() if h not in prev]
    print('paths',len(paths),'unique',len(groups),'new to evaluate',len(todo),flush=True)
    with get_context('fork').Pool(NP) as pool: EV=dict(pool.map(ev,todo,chunksize=4))
    rows=[]
    for h,ps in groups.items():
        e=prev.get(h) or EV.get(ps[0])
        if e is None: continue
        # representative: first source-named path with provenance, else first source-named, else first
        def score(p):
            l,n=nm(p); k=(l,n); return (nonsrc(n,''),k not in P and k not in LR)
        ps2=sorted(ps,key=score); p=ps2[0]; lane,name=nm(p)
        pr=P.get((lane,name)) or {}; lr=LR.get((lane,name)) or {}
        sha=pr.get('sha') or lr.get('sha')
        kb='old' if sha in OLDS else 'new' if sha in NEWS else ('older' if sha else None)
        base=kb if kb in ('old','new') else ('new' if e['d_new']<=e['d_old'] else 'old')
        r={'lane':lane,'name':name,'path':p,'sha1':h,'ev':e,'bytes':e['bytes'],'M':e['M'],'d_new':e['d_new'],'d_old':e['d_old'],
           'base':base,'base_sha':sha,'base_known':kb,'genes':pr.get('genes'),'resfile':pr.get('src'),'hyp':lr.get('hyp'),
           'dups':[x[len(C)+1:] for x in ps2[1:7]]}
        r['nonsrc']=nonsrc(name,(r['genes'] or '')+' '+(r['hyp'] or ''))
        if kb=='older': r['excluded']='older source'
        if base=='new':
            r['tbytes']=e['bytes']; r['tM']=e['M']
            r['tmh']=bool(kb is None and e['d_old']<=e['d_new']+12 and e['tmh_old'])
            src=open(p,'rb').read()
        else:
            r['tbytes']=e['tr_bytes']; r['tM']=e['tr_M']; r['tmh']=e['tmh_old']
            src=translate(open(p,'rb').read()) if e['tr_bytes'] is not None else None
        if src is not None and not r.get('excluded'):
            tp=f"{TX}/{lane}__{name}__{h[:12]}.bin"
            if not os.path.exists(tp): open(tp,'wb').write(src)
            r['tpath']=tp
        else: r['tpath']=None; r['tM']=r['tM'] if src is not None else None
        r['dM']=(r['tM']-2251) if r.get('tM') is not None else None
        r['dB']=(r['tbytes']-27400) if r.get('tbytes') is not None else None
        rows.append(r)
    # this lane's own new-main captures
    for f in glob.glob(ME+'/res-5998913.jsonl'):
        for l in open(f):
            x=json.loads(l)
            if 'error' in x or x['name']=='m0': continue
            fb=f"{ME}/rx/{x['name']}/fn.bin"
            if not os.path.exists(fb): continue
            rows.append({'lane':'w16a17-cto-stitch16','name':x['name'],'path':fb,'sha1':None,'bytes':x['bytes'],'M':x['M'],'base':'new','base_sha':'5998913',
                'base_known':'new','genes':x['genes'],'resfile':'res-5998913.jsonl','hyp':'stitch16 recapture on 599891304: '+x['genes'],'nonsrc':False,
                'tbytes':x['bytes'],'tM':x['M'],'tpath':fb,'tmh':False,'dM':x['M']-2251,'dB':x['bytes']-27400,'dups':[],'d_new':None,'d_old':None})
    rows.sort(key=lambda r:-(r.get('tM') or 0))
    json.dump(rows,open(out,'w'),indent=0)
    import collections
    print('done',len(rows),collections.Counter(r['base_known'] for r in rows),'usable',sum(1 for r in rows if r.get('tpath') and not r['nonsrc'] and not r['tmh']),flush=True)
