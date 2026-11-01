#!/usr/bin/env python3
"""nt16.py <cat.json> <out.json> 'name+name' ...: price composites of catalogued captures on the current main with the
splice oracle and the w16 drift metrics (rfj true LCS = skeleton match under frame+register+jump masks, jump
displacement mismatches, region drift). Names may be lane/name to disambiguate. Experiment only."""
import sys,os,json,subprocess,tempfile
T=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,T)
import splice
ME=os.path.dirname(T)
NEWB=open(ME+'/rx/main/fn.bin','rb').read(); B=splice.parse(NEWB); BT=splice.targets(B)
def find(cat,n):
    if n.startswith('me/'):
        nm=n[3:]; fb=ME+'/rx/'+nm+'/fn.bin'; raw=open(fb,'rb').read()
        return {'lane':'w16a17-cto-stitch16','name':nm,'genes':nm,'dB':len(raw)-27400,'dM':splice.M(raw)-2251,'tpath':fb}
    if '/' in n:
        l,nm=n.split('/',1); xs=[x for x in cat if x['lane'].startswith(l) and x['name']==nm]
    else: xs=[x for x in cat if x['name']==n]
    xs=[x for x in xs if x['tpath'] and not x.get('excluded')]
    if not xs: raise SystemExit('not found: '+n)
    return xs[0]
def drift(raw):
    f=tempfile.NamedTemporaryFile(suffix='.bin',delete=False); f.write(raw); f.close()
    p=subprocess.run(['python3',T+'/drift.py',f.name],capture_output=True,text=True); os.unlink(f.name)
    return json.loads(p.stdout.strip().splitlines()[-1])
if __name__=='__main__':
    cat=json.load(open(sys.argv[1])); out=[]
    for spec in sys.argv[3:]:
        xs=[find(cat,n) for n in spec.split('+')]
        s=splice.splice(NEWB,[splice.Var(B,open(x['tpath'],'rb').read()) for x in xs],B,BT)
        if s is None: r={'composite':spec,'conflict':True}
        else:
            d=drift(s); r={'composite':spec,'bytes':len(s),'M':d['M'],'rfj_lcs':d['rfj_lcs'],'jumps_bad':d['jumps_bad'],'jumps_aligned':d['jumps_aligned'],
                          'drift_med':d['drift_med'],'parts':[{'lane':x['lane'],'name':x['name'],'genes':x['genes'],'dB':x['dB'],'dM':x['dM']} for x in xs]}
        print(json.dumps(r),flush=True); out.append(r)
    json.dump(out,open(sys.argv[2],'w'),indent=1)
