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
# ---- S16: CtoState creator field through a pointer / explicit copy (original copies it ascending from r9=&curve.creator) ----
_ST='let st=CtoState{fee_configurable:a.global.creator_fee_configurable,creator:a.bonding_curve.creator,'
_QL='let quote_locked={let q=a.bonding_curve.quote_mint;'
G['csA']=[(_QL,'let cref=&a.bonding_curve.creator;'+_QL),(_ST,'let st=CtoState{fee_configurable:a.global.creator_fee_configurable,creator:*cref,')]
G['csC']=[(_ST,'let st=CtoState{fee_configurable:a.global.creator_fee_configurable,creator:Pubkey::new_from_array(a.bonding_curve.creator.to_bytes()),')]
G['csF']=[(_ST,'let creator=a.bonding_curve.creator;let st=CtoState{fee_configurable:a.global.creator_fee_configurable,creator,')]
G['csH']=[(_SH0,'let cref=&a.bonding_curve.creator;let shared={let sk=a.sharing_config.key();*cref==sk}&&a.sharing_config.owner==&FEES&&!a.sharing_config.data_is_empty();'),(_ST,'let st=CtoState{fee_configurable:a.global.creator_fee_configurable,creator:*cref,')]
G['csI']=[(_ST,'let st=CtoState{fee_configurable:a.global.creator_fee_configurable,creator:{let c:&Pubkey=&a.bonding_curve.creator;*c},')]
# ---- S16: curve flags read early (the original loads is_mayhem_mode/is_holder_reward/is_cashback_coin right after the
#      shared test, spills them, and stores them into CtoState later; main loads them at the CtoState literal) ----
_STF='mayhem:a.bonding_curve.is_mayhem_mode,holder_reward:a.bonding_curve.is_holder_reward,cashback:a.bonding_curve.is_cashback_coin,'
_FL='let mayhem=a.bonding_curve.is_mayhem_mode;let holder_reward=a.bonding_curve.is_holder_reward;let cashback_coin=a.bonding_curve.is_cashback_coin;'
G['fl1']=[(_QL,_FL+_QL),(_STF,'mayhem,holder_reward,cashback:cashback_coin,')]
G['fl2']=[('let holder_key;let hk=',_FL+'let holder_key;let hk='),(_STF,'mayhem,holder_reward,cashback:cashback_coin,')]
G['fl3']=[(_QL,'let flags=(a.bonding_curve.is_mayhem_mode,a.bonding_curve.is_holder_reward,a.bonding_curve.is_cashback_coin);'+_QL),(_STF,'mayhem:flags.0,holder_reward:flags.1,cashback:flags.2,')]
# ---- W17 (stitch16 continuation): the original's entry flag order is cashback(0xa3)->spill, holder_reward(0xa5)->spill,
#      mayhem(0xa2)->r8, right after the shared test (orig 0x290-0x2b0); fl1 loads mayhem, holder, cashback ----
_FL4='let cashback_coin=a.bonding_curve.is_cashback_coin;let holder_reward=a.bonding_curve.is_holder_reward;let mayhem=a.bonding_curve.is_mayhem_mode;'
G['fl4']=[(_QL,_FL4+_QL),(_STF,'mayhem,holder_reward,cashback:cashback_coin,')]
_FL5='let cashback_coin=a.bonding_curve.is_cashback_coin;let holder_reward=a.bonding_curve.is_holder_reward;'
G['fl5']=[(_QL,_FL5+_QL),(_STF,'mayhem:a.bonding_curve.is_mayhem_mode,holder_reward,cashback:cashback_coin,')]
_FL6='let holder_reward=a.bonding_curve.is_holder_reward;let cashback_coin=a.bonding_curve.is_cashback_coin;let mayhem=a.bonding_curve.is_mayhem_mode;'
G['fl6']=[(_QL,_FL6+_QL),(_STF,'mayhem,holder_reward,cashback:cashback_coin,')]
# ---- W17 shim knobs (w17a03 vload screen L2735/L2737: a volatile CtoState flag load is -16 B at 0 M on main) ----
G['vL2735']=[('cashback:a.bonding_curve.is_cashback_coin,quote_locked','cashback:unsafe{core::ptr::read_volatile(&a.bonding_curve.is_cashback_coin)}/*shim: pins the CtoState cashback load (w17a03 L2735)*/,quote_locked')]
G['vL2737']=[('holder_enabled:a.global.is_holder_reward_enabled};','holder_enabled:unsafe{core::ptr::read_volatile(&a.global.is_holder_reward_enabled)}/*shim: pins the CtoState holder_enabled load (w17a03 L2737)*/};')]
