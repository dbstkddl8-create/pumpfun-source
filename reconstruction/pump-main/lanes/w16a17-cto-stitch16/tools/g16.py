# w16a17 stitch16 gene library: union of the cached libraries, applied to the CURRENT admin_cto source (599891304).
# Precedence (first wins): w16a02 genes_fk, w15a16 genes_mp (includes w15a03 genes_s15), w15a13 e/<name>.py as j13:<name>,
# w16a07 e/<name>.py as a07:<name>, plus this lane's own genes (S16 below). Experiment only.
import os,sys,runpy,glob
_T=os.path.dirname(os.path.abspath(__file__)); _O=os.path.dirname(_T)
sys.path.insert(0,_T)
import genes_fk as _FK
sys.path.insert(0,_O+'/glib/w15a03-cto-stitch15'); sys.path.insert(0,_O+'/glib/w15a16-cto-mpermrank')
import genes_mp as _MP
G={}
for _k,_v in _MP.G.items(): G[_k]=_v
for _k,_v in _FK.G.items(): G[_k]=_v           # w16a02 definitions win (same text for the shared names)
_C=os.path.expanduser('~/.cache/pumpfun-reconstruction/lanes')
for _f in glob.glob(_C+'/w15a13-cto-jointraceback/e/*.py'):
    try: G['j13:'+os.path.basename(_f)[:-3]]=list(runpy.run_path(_f)['EDITS'])
    except Exception: pass
for _f in glob.glob(_C+'/w16a07-cto-sweeptuple/e/*.py'):
    try: G['a07:'+os.path.basename(_f)[:-3]]=list(runpy.run_path(_f)['EDITS'])
    except Exception: pass
sys.path.insert(0,_O+'/glib')
import lit as _LIT
def _litgene(n):
    # 'lit:<key>:<order>' = w15a30 lit.py struct-literal field permutation (order in 0-9a-j digits)
    _,k,o=n.split(':'); order=['0123456789abcdefghij'.index(c) for c in o]
    return [lambda s,k=k,order=order:_LIT.permute(s,k,order)]
def apply(s,names):
    for n in names:
        if n.startswith('lit:') and n not in G: G[n]=_litgene(n)
        for e in G[n]:
            if callable(e): s=e(s); continue
            if len(e)==3: a,b,k=e
            else: (a,b),k=e,1
            c=s.count(a)
            if c!=k: raise Exception(f'gene {n}: {c} occurrences (want {k}) of {a[:120]!r}')
            s=s.replace(a,b)
    return s
# ---- this lane (S16): w15a21 creatorcopy g1-family genes (texts from the ledger rows 0x22a10-w15-86e2a6b-creatorcopy-*) ----
_VAL='let mut target=validate(&st,hopt,fee,new,&holder_key,&sk)?;'
_ARM='else{sharing_update=Some(args.0);target=a.bonding_curve.creator;(false'
G['cs7']=[(_VAL,'let creator=st.creator;'+_VAL),(_ARM,'else{target=creator;sharing_update=Some(args.0);(false')]
G['tf_f6']=[(_VAL,'let creator=a.bonding_curve.creator;'+_VAL),(_ARM,'else{target=creator;sharing_update=Some(args.0);(false')]
# ---- S16: one entry creator copy shared by the shared test and the shared-arm target override (crl3 x g1) ----
_SH0='let shared={let sk=a.sharing_config.key();a.bonding_curve.creator==sk}&&a.sharing_config.owner==&FEES&&!a.sharing_config.data_is_empty();'
_TG0='sharing_update=Some(args.0);target=a.bonding_curve.creator;'
G['crlT1']=[(_SH0,'let cr=a.bonding_curve.creator;let shared=cr==a.sharing_config.key()&&a.sharing_config.owner==&FEES&&!a.sharing_config.data_is_empty();'),(_TG0,'sharing_update=Some(args.0);target=cr;')]
G['crlT3']=[(_SH0,'let cr=a.bonding_curve.creator;let shared={let sk=a.sharing_config.key();cr==sk}&&a.sharing_config.owner==&FEES&&!a.sharing_config.data_is_empty();'),(_TG0,'sharing_update=Some(args.0);target=cr;')]
G['crlT4']=G['crlT1']+[('let st=CtoState{fee_configurable:a.global.creator_fee_configurable,creator:a.bonding_curve.creator,','let st=CtoState{fee_configurable:a.global.creator_fee_configurable,creator:cr,')]
G['crlT5']=[G['crlT1'][0],G['crlT4'][2]]
G['crlT6']=[(_SH0,'let cr=&a.bonding_curve.creator;let shared=*cr==a.sharing_config.key()&&a.sharing_config.owner==&FEES&&!a.sharing_config.data_is_empty();'),(_TG0,'sharing_update=Some(args.0);target=*cr;')]
# ---- S16: event Clock spellings (sh_iflet's pay band on 1f4e396 is the event's Clock/emit_cpi Err paths) ----
_TS='timestamp:Clock::get()?.unix_timestamp,authority:a.admin_set_creator_authority.key(),mint,bonding_curve'
G['ts_mapf']=[(_TS,'timestamp:Clock::get().map(|c|c.unix_timestamp)?,authority:a.admin_set_creator_authority.key(),mint,bonding_curve')]
G['ts_errf']=[(_TS,'timestamp:Clock::get().map_err(anchor_lang::error::Error::from)?.unix_timestamp,authority:a.admin_set_creator_authority.key(),mint,bonding_curve')]
G['ts_blk']=[(_TS,'timestamp:{let c=Clock::get()?;c.unix_timestamp},authority:a.admin_set_creator_authority.key(),mint,bonding_curve')]
G['ts_sysv']=[(_TS,'timestamp:<Clock as anchor_lang::solana_program::sysvar::Sysvar>::get()?.unix_timestamp,authority:a.admin_set_creator_authority.key(),mint,bonding_curve')]
G['ts_q']=[(_TS,'timestamp:(Clock::get()?).unix_timestamp,authority:a.admin_set_creator_authority.key(),mint,bonding_curve')]
