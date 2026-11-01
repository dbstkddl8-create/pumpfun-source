#!/usr/bin/env python3
"""mkcat16.py <cat16.json> <out sizeknobs json> [--min-m 2150]: compact, committed form of the cat16 catalog on the
current main (599891304 = 1f4e396 admin_cto source, A6+ev6): one row per usable source capture with its byte delta and
M on the new main (translated for old-source captures), its base and provenance, where the bytes land (region.py,
call-anchor alignment against the new main) and the w16 drift metrics for near-main rows. Experiment only."""
import sys,os,json,re,subprocess
T=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,T)
import region
ME=os.path.dirname(T)
NS=re.compile(r'(ra$|Br$|TB$|^mpp_|^mp_|^jt_|^spl_|__r|p2|perm|^fs_|^B$)')
def main():
    a=sys.argv[1:]; minm=2150
    if '--min-m' in a: i=a.index('--min-m'); minm=int(a[i+1]); del a[i:i+2]
    cat=json.load(open(a[0])); rows=[]
    for x in cat:
        if x['tM'] is None or x['tM']<minm or x['nonsrc'] or NS.search(x['name']) or x.get('excluded'): continue
        r={'name':x['name'],'lane':x['lane'],'genes':x['genes'],'base':x['base'],'base_sha':x.get('base_sha'),
           'tbytes':x['tbytes'],'dB':x['dB'],'tM':x['tM'],'dM':x['dM'],'ratio':round(2*x['tM']/(6676+x['dB']/8),5),
           'touches_main_hunks':bool(x.get('tmh')),'d_new':x['d_new'],'hyp':(x.get('hyp') or '')[:160]}
        if x.get('alias_of'): r['alias_of']=x['alias_of']
        rg=region.regions(x['tpath'],ME+'/rx/main/fn.bin'); r['by_region']=rg.get('by_region'); r['call_note']=rg.get('error')
        if abs(x['dB'])<=200 and x['tM']>=2236:
            p=subprocess.run(['python3',T+'/drift.py',x['tpath']],capture_output=True,text=True)
            try: r.update({k:v for k,v in json.loads(p.stdout.strip().splitlines()[-1]).items() if k in ('rfj_lcs','jumps_bad','jumps_aligned','drift_med')})
            except Exception: pass
        rows.append(r)
    rows.sort(key=lambda r:(-r['tM'],abs(r['dB'])))
    out={'lane':'w16a17-cto-stitch16','target':'0x22a10 admin_cto::execute','pinned_bytes':27400,
         'base':{'main':'599891304 (admin_cto.rs = 1f4e396: A6 + ev6)','M':2251,'ratio':0.67436,'slots':3141,'rfj_lcs':3001,'jumps_bad':112,'jumps_aligned':262},
         'how_to_read':('One row per cached raw-IR source capture (w15/w16 lanes) that is usable on the current main. base=old rows were '
           'built on the 9bd38c7/86e2a6b/9120883/1cc4879 admin_cto source and are translated onto A6+ev6 with the splice oracle '
           '(splice(old main,[new main, capture])); base=new rows were built on 1f4e396/5998913. touches_main_hunks=true means the '
           'capture changes code inside the A6/ev6 hunks, so its translation is unreliable (screens skip it). Captures on older '
           'sources (90300f9 and before) are left out. tbytes/dB/tM/dM are on the new main (M 2,251 = 0.67436). by_region: where '
           'the byte delta lands (E entry, V validate+tree, SH sweep head, TC TCF, SC sharing-CPI build, PC post-CPI pool/event, '
           'ER error blocks, NA sweep native arm, WA wallet, TL tail; new-main candidate offsets). rfj_lcs/jumps_bad/drift_med: '
           'w16 drift metrics (main 3001 / 112 / entry -22).'),
         'knobs':rows}
    json.dump(out,open(a[1],'w'),separators=(',',':'))
    t=open(a[1]).read().replace('{"name":','\n{"name":'); open(a[1],'w').write(t)
    print(len(rows),'rows')
if __name__=='__main__': main()
