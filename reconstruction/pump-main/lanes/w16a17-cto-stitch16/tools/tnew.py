#!/usr/bin/env python3
"""tnew.py: translate catalog captures (on 5998913 source) onto the new main (rx/rc0 = 442ae70 admin_cto: v4320 + rc1964)
with the splice oracle and price them; then size-complementary pairs at 27,400 B. Experiment only."""
import sys,os,json,itertools
sys.path.insert(0,'tools'); import splice
OLD=open('rx/main/fn.bin','rb').read(); NEW=open('rx/rc0/fn.bin','rb').read()
OB=splice.parse(OLD); OBT=splice.targets(OB); NV=splice.Var(OB,NEW)
R=json.load(open('data/cat16_r4.json'))
rows=[r for r in R if r.get('tpath') and not r.get('nonsrc') and not r.get('tmh') and not r.get('excluded') and r.get('tM') and r['tM']>=2236 and abs(r['tbytes']-27400)<=96]
# add own w16 captures on 5998913
for n in ['g1','crl3','C3b','crl3t1n','g1t1n','G1d','G1i','t1n','I6n','hkl3','lfb5','ntA','ntB','q5','hkcopy','S1','S2','a1','shif','cuunw','wlwe','colnat','gwclk','csF','L1','C3a']:
    p=f'rx/{n}/fn.bin'
    if os.path.exists(p): rows.append({'lane':'w16a17(own)','name':n,'tpath':p,'tbytes':len(open(p,'rb').read()),'tM':None})
print('rows',len(rows),flush=True)
out=[]; seen=set()
for r in rows:
    raw=open(r['tpath'],'rb').read()
    if raw in seen: continue
    seen.add(raw)
    s=splice.splice(OLD,[NV,raw],OB,OBT)
    if s is None: continue
    out.append({'lane':r['lane'],'name':r['name'],'tpath':r['tpath'],'old_bytes':r['tbytes'],'old_M':r.get('tM'),'bytes':len(s),'M':splice.M(s)})
out.sort(key=lambda x:(-x['M'],x['bytes']))
json.dump(out,open('w17/tnew.json','w'),indent=0)
print('translated',len(out))
for x in out[:25]: print(f"{x['lane'][:22]:22s} {x['name'][:26]:26s} old {x['old_bytes']}/{x['old_M']} -> new {x['bytes']}/{x['M']} ({x['M']-2257:+d})")
print('--- at 27400 best')
for x in [x for x in out if x['bytes']==27400][:12]: print(f"{x['lane'][:22]:22s} {x['name'][:26]:26s} {x['M']} ({x['M']-2257:+d})")
