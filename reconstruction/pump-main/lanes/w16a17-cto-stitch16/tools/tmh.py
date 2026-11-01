#!/usr/bin/env python3
"""tmh.py <cat.json> [NP]: flag old-base captures whose own diff against the old main touches the A6/ev6 hunks
(old main token ranges [1115,1133] and [2425,2495]); their translation onto the new main is unreliable (double
application of ev6/A6 or a conflict), so the screens skip them (field 'tmh'). Experiment only."""
import sys,os,json,difflib
from multiprocessing import get_context
T=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,T); import splice
ME=os.path.dirname(T)
OLD=open(ME+'/rx/main9bd/fn.bin','rb').read(); ON=[splice.norm(x) for x in splice.parse(OLD)]
R=[(1115,1133),(2425,2495)]
def f(p):
    X=[splice.norm(x) for x in splice.parse(open(p,'rb').read())]
    sm=difflib.SequenceMatcher(None,ON,X,autojunk=False)
    for t,i1,i2,j1,j2 in sm.get_opcodes():
        if t=='equal': continue
        for lo,hi in R:
            if i1<=hi and i2>=lo: return True
    return False
if __name__=='__main__':
    cat=json.load(open(sys.argv[1])); NP=int(sys.argv[2]) if len(sys.argv)>2 else 6
    idx=[k for k,x in enumerate(cat) if x['base']=='old' and x['tM'] is not None and 'tmh' not in x]
    with get_context('fork').Pool(NP) as P: res=P.map(f,[cat[k]['path'] for k in idx],chunksize=8)
    for k,r in zip(idx,res): cat[k]['tmh']=r
    for x in cat:
        if x['base']=='new': x['tmh']=False
    json.dump(cat,open(sys.argv[1],'w'),indent=0)
    print('flagged',sum(res),'of',len(idx))
