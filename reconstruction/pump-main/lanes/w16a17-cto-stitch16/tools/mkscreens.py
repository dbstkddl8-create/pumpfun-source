#!/usr/bin/env python3
"""mkscreens.py <out.json> <screen.jsonl>...: per-screen summary (priced count, M histogram at 27,400 B, top rows) for
the committed notes. Experiment only."""
import sys,os,json,collections
out={}
for f in sys.argv[2:]:
    if not os.path.exists(f): continue
    rows=[json.loads(l) for l in open(f) if l.strip()]
    at=[r for r in rows if r.get('bytes')==27400]
    h=collections.Counter(r['M'] for r in at)
    at.sort(key=lambda r:-r['M'])
    out[os.path.basename(f)]={'priced':len(rows),'at_27400':len(at),'hist_top':sorted(h.items())[-6:],
        'top':[{k:r.get(k) for k in ('names','lanes','deltas','Ms','bytes','M')} for r in at[:20]]}
json.dump(out,open(sys.argv[1],'w'),indent=1)
print({k:(v['priced'],v['hist_top'][-1] if v['hist_top'] else None) for k,v in out.items()})
