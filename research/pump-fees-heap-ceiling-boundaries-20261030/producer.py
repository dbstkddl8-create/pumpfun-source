#!/usr/bin/env python3
"""Pump Fees heap ceilings, original vs rebuild.

Every outcome change of a size-driven input (declared or real String/Vec length
in instruction data, stored user_id / tier / shareholder length in an account)
is located to a single unit by bisection on each image, with and without a
ComputeBudget RequestHeapFrame. A family is a sweep of one variable x; the scan
samples a fixed grid and bisects every adjacent pair of grid points whose
outcome class differs. Outcome class = transaction error + Anchor error code.

Stored-length families use synthetic accounts longer than the program can
create; they are a ruler for the allocator, not reachable state.

usage: producer.py --root <repo> --images '{"original": p, "candidate": p}' --out <packet dir>
--images also accepts a path to a file holding that JSON object.
Deterministic: fixed key seeds, fixed clock, no paths in the output.
"""
import argparse, gzip, hashlib, json, pathlib, struct
from solders.account import Account
from solders.clock import Clock
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.litesvm import LiteSVM
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from solders.transaction_metadata import FailedTransactionMetadata

PROGRAM = Pubkey.from_string('pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ')
PUMP = Pubkey.from_string('6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P')
BUDGET = Pubkey.from_string('ComputeBudget111111111111111111111111111111')
TOKEN = Pubkey.from_string('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA')
ATA = Pubkey.from_string('ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL')
WSOL = Pubkey.from_string('So11111111111111111111111111111111111111112')
ZERO = Pubkey.default()
NOW = 1700000000
SEEDS = {'PAYER': 231, 'AUTH': 232, 'OTHER': 233, 'RECIPIENT': 234}
KP = {k: Keypair.from_seed(bytes([v]) * 32) for k, v in SEEDS.items()}
GLOBAL, GLOBAL_BUMP = Pubkey.find_program_address([b'fee-program-global'], PROGRAM)
CONFIG, CONFIG_BUMP = Pubkey.find_program_address([b'fee_config', bytes(PUMP)], PROGRAM)
EVENT = Pubkey.find_program_address([b'__event_authority'], PROGRAM)[0]
MINT = Pubkey.from_bytes(bytes([71]) * 32)
SHARING, SHARING_BUMP = Pubkey.find_program_address([b'sharing-config', bytes(MINT)], PROGRAM)
POOL_AUTH = Pubkey.find_program_address([b'pool-authority', bytes(MINT)], PUMP)[0]
PUMP_GLOBAL = Pubkey.find_program_address([b'global'], PUMP)[0]
FRAMES = [None, 32768, 33792, 65536, 131072, 262144]
CU_LIMIT = 1400000


def disc(name, kind='global'):
    return hashlib.sha256(f'{kind}:{name}'.encode()).digest()[:8]


def ata(owner):
    return Pubkey.find_program_address([bytes(owner), bytes(TOKEN), bytes(WSOL)], ATA)[0]


def social_key(uid, platform=0):
    return Pubkey.find_program_address([b'social-fee-pda', uid, bytes([platform])], PROGRAM)


def tier_bytes(n):
    return struct.pack('<I', n) + b''.join((i * 10).to_bytes(16, 'little') + struct.pack('<QQQ', 1, 1, 1) for i in range(n))


def holder_bytes(n):
    return struct.pack('<I', n) + b''.join(bytes([7]) * 32 + struct.pack('<H', 1) for _ in range(n))


def arg_bytes(p):
    x = p['x']
    t = p['arg']
    if t == 'str-declared':
        return disc(p['ix']) + struct.pack('<I', x)
    if t == 'str-ascii':
        return disc(p['ix']) + struct.pack('<I', x) + b'a' * x + bytes(1)
    if t == 'str-invalid':
        return disc(p['ix']) + struct.pack('<I', x) + b'\xff' * x + bytes(1)
    if t == 'vec-tier':
        return disc(p['ix']) + tier_bytes(x) + bytes(p.get('tail', 0))
    if t == 'vec-holder':
        return disc(p['ix']) + holder_bytes(x)
    raise ValueError(t)


def global_data(flags=0, rate=0):
    return disc('FeeProgramGlobal', 'account') + bytes([GLOBAL_BUMP]) + bytes(KP['AUTH'].pubkey()) + bytes([flags]) + bytes(KP['AUTH'].pubkey()) + rate.to_bytes(8, 'little') + bytes(256)


def social_data(p, stored, bump):
    uid = b's' * stored
    last = NOW - 1 if p.get('rate') else 0
    d = disc('SocialFeePda', 'account') + bytes([bump, 1]) + struct.pack('<I', stored) + uid + bytes(1) + bytes(8) + last.to_bytes(8, 'little') + bytes(8) + bytes(120)
    return d


def config_data(normal, stable):
    d = disc('FeeConfig', 'account') + bytes([CONFIG_BUMP]) + bytes(KP['AUTH'].pubkey()) + struct.pack('<QQQ', 1, 1, 1) + tier_bytes(normal) + tier_bytes(stable) + struct.pack('<QQQ', 1, 1, 1)
    return d.ljust(4097, b'\0')


def sharing_data(n):
    d = disc('SharingConfig', 'account') + bytes([SHARING_BUMP, 1, 1]) + bytes(MINT) + bytes(KP['AUTH'].pubkey()) + bytes(1) + holder_bytes(n)
    return d.ljust(1024, b'\0')


FEE_KINDS = ('get_fees', 'get_fees_quote', 'update', 'upsert', 'update_stable', 'upsert_stable', 'exotic', 'update_admin')


def meta(k, s, w):
    return AccountMeta(k, s, w)


def setup_and_ix(vm, p):
    kind = p['kind']
    x = p['x']
    if kind == 'raw':
        return arg_bytes(p), []
    if kind in ('claim', 'claim_v2'):
        long_uid = p.get('var') == 'incoming'
        uid = b'u' * (x if long_uid else p.get('uid', 8))
        # a seed over 32 bytes has no PDA; such a claim is pointed at the 32-byte user's account
        key, bump = social_key(uid[:32])
        stored = 8 if long_uid else x
        d = social_data(p, stored, bump)
        rent = vm.minimum_balance_for_rent_exemption(179)
        vm.set_account(key, Account(rent + p.get('surplus', 0), d, PROGRAM))
        vm.set_account(GLOBAL, Account(10**9, global_data(p.get('flags', 0), 100 if p.get('rate') else 0), PROGRAM))
        vm.set_account(KP['RECIPIENT'].pubkey(), Account(10**9, b'', ZERO))
        data = disc('claim_social_fee_pda' if kind == 'claim' else 'claim_social_fee_pda_v2') + struct.pack('<I', len(uid)) + uid + bytes(1)
        signer = KP['OTHER' if p.get('wrong_auth') else 'AUTH'].pubkey()
        rcp = KP['RECIPIENT'].pubkey()
        if kind == 'claim':
            return data, [meta(rcp, False, True), meta(key, False, True), meta(GLOBAL, False, False), meta(signer, True, False), meta(EVENT, False, False), meta(PROGRAM, False, False)]
        mint = bytearray(82)
        mint[44] = 9
        mint[45] = 1
        vm.set_account(WSOL, Account(10**9, bytes(mint), TOKEN))
        return data, [meta(rcp, False, True), meta(key, False, True), meta(WSOL, False, True), meta(ata(key), False, True), meta(ata(rcp), False, True), meta(TOKEN, False, False), meta(ATA, False, False), meta(GLOBAL, False, False), meta(signer, True, False), meta(ZERO, False, False), meta(EVENT, False, False), meta(PROGRAM, False, False)]
    if kind in FEE_KINDS:
        normal = p['normal'] if 'normal' in p else x if p.get('var', 'normal') == 'normal' else 2
        stable = x if p.get('var') == 'stable' else 0
        vm.set_account(CONFIG, Account(10**10, config_data(normal, stable), PROGRAM))
        if kind == 'get_fees':
            return disc('get_fees') + bytes([1]) + (0).to_bytes(16, 'little') + bytes(8) + bytes([p.get('quote', 0)]), [meta(CONFIG, False, False), meta(PUMP, False, False)]
        if kind == 'get_fees_quote':
            return disc('get_fees_with_quote_mint') + bytes([1]) + (0).to_bytes(16, 'little') + bytes(WSOL), [meta(CONFIG, False, False), meta(PUMP, False, False)]
        n = x if p.get('var') == 'incoming' else p.get('n', 1)
        admin = KP[p.get('signer', 'AUTH')].pubkey()
        tail = [meta(PUMP, False, False), meta(EVENT, False, False), meta(PROGRAM, False, False)]
        if kind == 'exotic':
            return disc('set_exotic_flat_fees') + struct.pack('<QQQ', 2, 2, 2), [meta(CONFIG, False, True), meta(admin, True, True), meta(PUMP, False, False), meta(ZERO, False, False), meta(EVENT, False, False), meta(PROGRAM, False, False)]
        if kind == 'update_admin':
            return disc('update_admin'), [meta(admin, True, False), meta(CONFIG, False, True), meta(KP['OTHER'].pubkey(), False, False)] + tail
        data = {'update': disc('update_fee_config') + tier_bytes(n) + struct.pack('<QQQ', 1, 1, 1),
                'upsert': disc('upsert_fee_tiers') + tier_bytes(n) + bytes(1),
                'update_stable': disc('update_stable_fee_config') + tier_bytes(n),
                'upsert_stable': disc('upsert_stable_fee_tiers') + tier_bytes(n) + bytes(1)}[kind]
        return data, [meta(CONFIG, False, True), meta(admin, True, False)] + tail
    if kind == 'cto':
        vm.set_account(SHARING, Account(10**8, sharing_data(x), PROGRAM))
        g = bytearray(1088)
        g[0:8] = disc('Global', 'account')
        g[8] = 1
        g[418:450] = bytes(KP['AUTH'].pubkey())
        vm.set_account(PUMP_GLOBAL, Account(10**9, bytes(g), PUMP))
        mint = bytearray(82)
        mint[44] = 6
        mint[45] = 1
        vm.set_account(MINT, Account(10**9, bytes(mint), TOKEN))
        arg = bytes([1]) + bytes(KP['OTHER'].pubkey()) if p.get('new') else bytes(1)
        return disc('admin_cto_sharing_config') + arg, [meta(POOL_AUTH, True, False), meta(KP['AUTH'].pubkey(), True, False), meta(PUMP_GLOBAL, False, False), meta(MINT, False, False), meta(SHARING, False, True), meta(EVENT, False, False), meta(PROGRAM, False, False)]
    raise ValueError(kind)


def new_vm(binary):
    vm = LiteSVM().with_transaction_history(0).with_log_bytes_limit(None).with_sigverify(False)
    vm.add_program_from_file(PROGRAM, binary)
    return vm


def execute(vm, p):
    vm.expire_blockhash()
    vm.set_clock(Clock(1000, 0, 0, 0, NOW))
    for k in KP.values():
        vm.set_account(k.pubkey(), Account(10**12, b'', ZERO))
    data, metas = setup_and_ix(vm, p)
    ixs = [Instruction(BUDGET, b'\x02' + struct.pack('<I', CU_LIMIT), [])]
    if p.get('heap'):
        ixs.append(Instruction(BUDGET, b'\x01' + struct.pack('<I', p['heap']), []))
    ixs.append(Instruction(PROGRAM, data, metas))
    payer = KP['PAYER']
    msg = Message.new_with_blockhash(ixs, payer.pubkey(), vm.latest_blockhash())
    tx = Transaction.new_unsigned(msg)
    signers = [payer] + [k for k in KP.values() if k.pubkey() != payer.pubkey() and any(m.pubkey == k.pubkey() and m.is_signer for m in metas)]
    tx.partial_sign(signers, vm.latest_blockhash())
    r = vm.send_transaction(tx)
    failed = isinstance(r, FailedTransactionMetadata)
    md = r.meta() if failed else r
    logs = list(md.logs())
    cu = md.compute_units_consumed
    rd = bytes(md.return_data().data)
    return {
        'error': str(r.err()) if failed else None,
        'custom_error': next((l.split('Error Code: ')[1].split('.')[0] for l in logs if 'Error Code: ' in l), None),
        'oom': any('memory allocation failed' in l for l in logs),
        'oom_after_event_log': any(l.startswith('Program data:') for l in logs),
        'compute_units': cu() if callable(cu) else cu,
        'logs': logs,
        'return_data_len': len(rd),
        'return_data_sha256': hashlib.sha256(rd).hexdigest(),
    }


def klass(res):
    if res['error'] is None:
        return 'ok'
    if res['oom']:
        return 'OOM'
    if res['custom_error']:
        return res['custom_error']
    if any('Return data too large' in l for l in res['logs']):
        return 'ReturnDataTooLarge'
    e = res['error']
    return e.split('Tagged(')[-1].split('Fieldless(')[-1].rstrip(')')


def receipt(res):
    # log lines can hold whole events; receipts keep each line's first 160 bytes plus a hash of the full list
    return {'error': res['error'], 'custom_error': res['custom_error'], 'oom': res['oom'], 'oom_after_event_log': res['oom_after_event_log'], 'compute_units': res['compute_units'],
            'logs_sha256': hashlib.sha256('\n'.join(res['logs']).encode()).hexdigest(), 'log_lines': [l[:160] for l in res['logs']],
            'return_data_len': res['return_data_len'], 'return_data_sha256': res['return_data_sha256']}


def grid(lo, hi, n=48):
    # short ranges (Vec counts) are walked point by point
    if hi - lo <= 2000:
        return list(range(lo, hi + 1))
    xs = {lo, hi}
    for i in range(1, n):
        xs.add(lo + round((hi - lo) * (i / n) ** 2))
    return sorted(xs)


def fam(name, handler, x, lo, hi, **p):
    return {'name': name, 'handler': handler, 'x': x, 'lo': lo, 'hi': hi, 'params': p}


def families():
    out = []
    strings = ['create_social_fee_pda', 'claim_social_fee_pda', 'claim_social_fee_pda_v2']
    for ix in strings:
        out.append(fam(f'declared-string-{ix}', ix, 'declared user_id length, no body, no accounts', 1, 70000, kind='raw', arg='str-declared', ix=ix))
    for h in FRAMES[1:]:
        out.append(fam(f'declared-string-frame-{h}', strings[0], 'declared user_id length, no body, no accounts', 1, 300000, kind='raw', arg='str-declared', ix=strings[0], heap=h))
    for ix in strings:
        out.append(fam(f'ascii-body-{ix}', ix, 'user_id length with an ASCII body, no accounts', 1, 40000, kind='raw', arg='str-ascii', ix=ix))
        out.append(fam(f'invalid-utf8-body-{ix}', ix, 'user_id length with a 0xff body, no accounts', 1, 40000, kind='raw', arg='str-invalid', ix=ix))
    out.append(fam('ascii-body-frame-262144', strings[0], 'user_id length with an ASCII body, no accounts', 1, 40000, kind='raw', arg='str-ascii', ix=strings[0], heap=262144))
    for ix, tail in [('update_fee_config', 24), ('update_stable_fee_config', 0), ('upsert_fee_tiers', 1), ('upsert_stable_fee_tiers', 1)]:
        out.append(fam(f'tier-vec-{ix}', ix, 'Vec<FeeTier> length with a body, no accounts', 1, 440, kind='raw', arg='vec-tier', ix=ix, tail=tail))
    out.append(fam('tier-vec-frame-262144', 'update_fee_config', 'Vec<FeeTier> length with a body, no accounts', 1, 440, kind='raw', arg='vec-tier', ix='update_fee_config', tail=24, heap=262144))
    for ix in ['update_fee_shares', 'update_fee_shares_v2']:
        out.append(fam(f'holder-vec-{ix}', ix, 'Vec<Shareholder> length with a body, no accounts', 1, 520, kind='raw', arg='vec-holder', ix=ix))
    out.append(fam('holder-vec-frame-262144', 'update_fee_shares', 'Vec<Shareholder> length with a body, no accounts', 1, 520, kind='raw', arg='vec-holder', ix='update_fee_shares', heap=262144))
    st = 'stored user_id length'
    cl = 'claim_social_fee_pda'
    out.append(fam('claim-pays', cl, st, 0, 34000, kind='claim', surplus=1000))
    out.append(fam('claim-pays-uid32', cl, st + ', 32-byte incoming user_id', 0, 34000, kind='claim', surplus=1000, uid=32))
    out.append(fam('claim-pays-frame-262144', cl, st, 0, 34000, kind='claim', surplus=1000, heap=262144))
    out.append(fam('claim-nothing-due', cl, st, 0, 34000, kind='claim'))
    out.append(fam('claim-rate-limited', cl, st, 0, 34000, kind='claim', surplus=1000, rate=1))
    out.append(fam('claim-disabled', cl, st, 0, 34000, kind='claim', surplus=1000, flags=2))
    out.append(fam('claim-wrong-authority', cl, st, 0, 34000, kind='claim', surplus=1000, wrong_auth=1))
    out.append(fam('claim-v2-native-pays', 'claim_social_fee_pda_v2', st, 0, 34000, kind='claim_v2', surplus=1000))
    out.append(fam('claim-long-incoming', cl, 'incoming user_id length with a body, full accounts', 1, 34000, kind='claim', surplus=1000, var='incoming'))
    out.append(fam('claim-v2-native-nothing-due', 'claim_social_fee_pda_v2', st, 0, 34000, kind='claim_v2'))
    tn = 'stored fee_tiers length'
    out.append(fam('get-fees-stored-normal', 'get_fees', tn, 0, 440, kind='get_fees'))
    out.append(fam('get-fees-stored-stable', 'get_fees', 'stored stable_fee_tiers length', 0, 440, kind='get_fees', var='stable', quote=1))
    out.append(fam('update-stored-normal-n1', 'update_fee_config', tn + ', 1 incoming tier', 0, 440, kind='update', n=1))
    out.append(fam('update-stored-normal-n50', 'update_fee_config', tn + ', 50 incoming tiers', 0, 440, kind='update', n=50))
    out.append(fam('update-stored-stable-n50', 'update_fee_config', 'stored stable_fee_tiers length, 50 incoming tiers', 0, 440, kind='update', n=50, var='stable'))
    out.append(fam('update-50-stored-both-n50', 'update_fee_config', 'stored stable_fee_tiers length, 50 stored fee_tiers, 50 incoming tiers', 0, 120, kind='update', n=50, var='stable', normal=50))
    out.append(fam('upsert-stored-normal-n1', 'upsert_fee_tiers', tn + ', 1 incoming tier at offset 0', 0, 440, kind='upsert', n=1))
    out.append(fam('get-fees-quote-stored-normal', 'get_fees_with_quote_mint', tn, 0, 440, kind='get_fees_quote'))
    out.append(fam('update-wrong-admin-stored-normal', 'update_fee_config', tn + ', non-admin signer', 0, 440, kind='update', signer='OTHER'))
    out.append(fam('update-stable-stored-stable-n1', 'update_stable_fee_config', 'stored stable_fee_tiers length, 1 incoming tier', 0, 440, kind='update_stable', var='stable'))
    out.append(fam('upsert-stable-stored-stable-n1', 'upsert_stable_fee_tiers', 'stored stable_fee_tiers length, 1 incoming tier at offset 0', 0, 440, kind='upsert_stable', var='stable'))
    out.append(fam('exotic-stored-normal', 'set_exotic_flat_fees', tn, 0, 440, kind='exotic'))
    out.append(fam('update-admin-stored-normal', 'update_admin', tn, 0, 440, kind='update_admin'))
    for name, handler, kind in [('update', 'update_fee_config', 'update'), ('update-stable', 'update_stable_fee_config', 'update_stable'), ('upsert', 'upsert_fee_tiers', 'upsert'), ('upsert-stable', 'upsert_stable_fee_tiers', 'upsert_stable')]:
        out.append(fam(f'{name}-incoming-full-accounts', handler, 'incoming Vec<FeeTier> length, full accounts, 2 stored tiers', 0, 440, kind=kind, var='incoming'))
    sh = 'stored shareholders length'
    out.append(fam('cto-revoke-stored-holders', 'admin_cto_sharing_config', sh + ', new_admin None', 0, 120, kind='cto'))
    out.append(fam('cto-new-admin-stored-holders', 'admin_cto_sharing_config', sh + ', new_admin Some', 0, 120, kind='cto', new=1))
    return out


def scan(vm, f):
    seen = {}

    def at(x):
        if x not in seen:
            seen[x] = execute(vm, dict(f['params'], x=x))
        return seen[x]
    xs = grid(f['lo'], f['hi'])
    edges = []
    # a class change inside a grid gap is walked down to adjacent x; each half is searched again
    stack = [(a, b) for a, b in zip(xs, xs[1:])]
    while stack:
        a, b = stack.pop()
        if klass(at(a)) == klass(at(b)):
            continue
        if b - a == 1:
            edges.append(a)
            continue
        m = (a + b) // 2
        stack += [(a, m), (m, b)]
    edges.sort()
    return {'grid': xs, 'edges': [{'x': a, 'below': klass(at(a)), 'above': klass(at(a + 1)), 'below_receipt': receipt(at(a)), 'above_receipt': receipt(at(a + 1))} for a in edges],
            'rows': [{'x': x, 'class': klass(at(x)), 'compute_units': at(x)['compute_units'], 'logs_sha256': receipt(at(x))['logs_sha256']} for x in xs]}


def strip_cu(lines):
    return [l for l in lines if not (' consumed ' in l and 'compute units' in l)]


def produce(images, fams):
    shas = {n: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for n, p in images.items()}
    vms = {n: new_vm(images[n]) for n in ['original', 'candidate']}
    receipts, summary = [], []
    for f in fams:
        o, k = scan(vms['original'], f), scan(vms['candidate'], f)
        same_edges = [(e['x'], e['below'], e['above']) for e in o['edges']] == [(e['x'], e['below'], e['above']) for e in k['edges']]
        receipts.append({'family': f, 'original': o, 'candidate': k})
        cu_diff = [{'x': a['x'], 'class': a['class'], 'original': a['compute_units'], 'candidate': b['compute_units']} for a, b in zip(o['rows'], k['rows']) if a['compute_units'] != b['compute_units']]
        log_diff = [a['x'] for a, b in zip(o['rows'], k['rows']) if a['logs_sha256'] != b['logs_sha256']]
        edge_cu = []
        for a, b in zip(o['edges'], k['edges']):
            for side in ['below_receipt', 'above_receipt']:
                if a[side]['compute_units'] != b[side]['compute_units'] or a[side]['logs_sha256'] != b[side]['logs_sha256']:
                    edge_cu.append({'x': a['x'], 'side': side, 'original_cu': a[side]['compute_units'], 'candidate_cu': b[side]['compute_units'],
                                    'logs_match': strip_cu(a[side]['log_lines']) == strip_cu(b[side]['log_lines'])})
        summary.append({'name': f['name'], 'handler': f['handler'], 'x': f['x'], 'heap_frame': f['params'].get('heap'),
                        'range': [f['lo'], f['hi']], 'grid_points': len(o['rows']),
                        'edges_original': [[e['x'], e['below'], e['above']] for e in o['edges']],
                        'edges_candidate': [[e['x'], e['below'], e['above']] for e in k['edges']],
                        'edges_match': same_edges, 'grid_classes_match': [r['class'] for r in o['rows']] == [r['class'] for r in k['rows']],
                        'grid_cu_diffs': cu_diff, 'grid_log_diffs': log_diff, 'edge_receipt_diffs': edge_cu,
                        'first_row_cu': o['rows'][0]['compute_units']})
    report = {'program_id': str(PROGRAM), 'signer_seeds': SEEDS, 'clock_unix': NOW, 'compute_unit_limit': CU_LIMIT,
              'scope': 'Pump Fees heap ceilings: every outcome change of a size-driven input located to one unit on each image, with and without RequestHeapFrame. Stored-length families use synthetic accounts.',
              'image_sha256': shas, 'family_count': len(summary),
              'edge_mismatched_families': [s['name'] for s in summary if not s['edges_match']],
              'grid_class_mismatched_families': [s['name'] for s in summary if not s['grid_classes_match']],
              'cu_or_log_diff_families': [s['name'] for s in summary if s['grid_cu_diffs'] or s['grid_log_diffs'] or s['edge_receipt_diffs']],
              'families': summary}
    return receipts, report


def gz(b):
    return gzip.compress(b, compresslevel=9, mtime=0)


def encode(receipts, report):
    rec = gz(b''.join(json.dumps(r, sort_keys=True, separators=(',', ':')).encode() + b'\n' for r in receipts))
    rep = gz(json.dumps(report, sort_keys=True, indent=1).encode() + b'\n')
    return rec, rep


def check_idl(root):
    idl = json.loads((root / 'evidence/upstream/pump_fees.json').read_text())
    assert idl['address'] == str(PROGRAM)
    ixs = {i['name']: bytes(i['discriminator']) for i in idl['instructions']}
    for f in families():
        assert ixs[f['handler']] == disc(f['handler']), f['handler']
    accs = {a['name']: bytes(a['discriminator']) for a in idl['accounts']}
    for n in ['SocialFeePda', 'FeeConfig', 'FeeProgramGlobal', 'SharingConfig']:
        assert accs[n] == disc(n, 'account'), n


def load_images(arg):
    arg = arg.strip()
    return json.loads(arg if arg.startswith('{') else pathlib.Path(arg).read_text())


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', required=True)
    p.add_argument('--images', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    images = load_images(a.images)
    check_idl(pathlib.Path(a.root))
    rec, rep = encode(*produce(images, families()))
    rt = pathlib.Path(a.out) / 'runtime'
    rt.mkdir(parents=True, exist_ok=True)
    (rt / 'receipts.jsonl.gz').write_bytes(rec)
    (rt / 'report.json.gz').write_bytes(rep)
    r = json.loads(gzip.decompress(rep))
    print(json.dumps({'families': r['family_count'], 'edge_mismatched': r['edge_mismatched_families'], 'grid_mismatched': r['grid_class_mismatched_families'], 'cu_log_diff': r['cu_or_log_diff_families']}))


if __name__ == '__main__':
    main()
