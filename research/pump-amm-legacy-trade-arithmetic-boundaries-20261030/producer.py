#!/usr/bin/env python3
"""pump_amm legacy single-hop trades (buy / buy_exact_quote_in / sell), original vs rebuilt image.

Each case builds a fresh LiteSVM with a synthetic GlobalConfig, Pool, FeeConfig and
GlobalVolumeAccumulator, plain SPL Token (or Token-2022 transfer-fee) quote accounts, one
pump_amm image plus LiteSVM's built-in token programs. The CPI target `get_fees_with_quote_mint`
is a stub that returns the case's (lp, protocol, creator) basis points as return data, in both
runs, so the fee bps are an input here and pump_fees itself is not under test.

Usage: producer.py --root <repo> --images '{"original": P, "candidate": P}' --out <dir>
"""
import argparse, gzip, hashlib, json, pathlib, re, struct
from solders.account import Account
from solders.clock import Clock
from solders.compute_budget import set_compute_unit_limit
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.litesvm import LiteSVM
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from solders.transaction_metadata import FailedTransactionMetadata

PROGRAM = Pubkey.from_string('pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA')
TOKEN = Pubkey.from_string('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA')
TOKEN22 = Pubkey.from_string('TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb')
ATA = Pubkey.from_string('ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL')
FEE_PROGRAM = Pubkey.from_string('pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ')
PUMP = Pubkey.from_string('6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P')
UPGRADEABLE = Pubkey.from_string('BPFLoaderUpgradeab1e11111111111111111111111')
SYSTEM = Pubkey.default()
EVENT = Pubkey.find_program_address([b'__event_authority'], PROGRAM)[0]
USER = Keypair.from_seed(bytes([207]) * 32)
CREATOR = Pubkey.from_bytes(bytes([11]) * 32)
COIN_CREATOR = Pubkey.from_bytes(bytes([12]) * 32)
BASE = Pubkey.from_bytes(bytes([21]) * 32)
QUOTE = Pubkey.from_bytes(bytes([22]) * 32)
LP = Pubkey.from_bytes(bytes([23]) * 32)
CONFIG = Pubkey.from_bytes(bytes([24]) * 32)
VBASE = Pubkey.from_bytes(bytes([34]) * 32)
VQUOTE = Pubkey.from_bytes(bytes([35]) * 32)
UBASE = Pubkey.from_bytes(bytes([36]) * 32)
UQUOTE = Pubkey.from_bytes(bytes([37]) * 32)
INDEX = 0
GVA = Pubkey.find_program_address([b'global_volume_accumulator'], PROGRAM)[0]
UVA = Pubkey.find_program_address([b'user_volume_accumulator', bytes(USER.pubkey())], PROGRAM)[0]
FEE_CONFIG, FEE_BUMP = Pubkey.find_program_address([b'fee_config', bytes(PROGRAM)], FEE_PROGRAM)
POOL_V2 = Pubkey.find_program_address([b'pool-v2', bytes(BASE)], PROGRAM)[0]


def disc(name):
    return hashlib.sha256(name.encode()).digest()[:8]


GLOBAL_DISC = bytes([149, 8, 156, 202, 160, 252, 176, 217])
POOL_DISC = bytes([241, 154, 109, 4, 17, 177, 109, 188])
MAX = 2**64 - 1
RECIPIENTS = [Pubkey.from_bytes(bytes([0x41 + i]) * 32) for i in range(8)]
RESERVED = Pubkey.from_bytes(bytes([0x61]) * 32)
RESERVED_LIST = [Pubkey.from_bytes(bytes([0x71 + i]) * 32) for i in range(7)]
BUYBACK = [Pubkey.from_bytes(bytes([0x91 + i]) * 32) for i in range(8)]
STRANGER = Pubkey.from_bytes(bytes([0x55]) * 32)


def creator_vault(cc):
    return Pubkey.find_program_address([b'creator_vault', bytes(cc)], PROGRAM)[0]


def ata(owner, m, program):
    return Pubkey.find_program_address([bytes(owner), bytes(program), bytes(m)], ATA)[0]


def pool_key(creator):
    return Pubkey.find_program_address(
        [b'pool', INDEX.to_bytes(2, 'little'), bytes(creator), bytes(BASE), bytes(QUOTE)], PROGRAM)


def mint(supply, decimals):
    d = bytearray(82)
    struct.pack_into('<I', d, 0, 1); d[4:36] = bytes([9]) * 32
    struct.pack_into('<Q', d, 36, supply); d[44] = decimals; d[45] = 1
    return bytes(d)


def tf_mint(base82, older, newer):
    """older/newer = (epoch, maximum_fee, bps): the two TransferFee entries of the extension."""
    d = bytearray(base82) + bytes(83) + bytes([1])
    conf = bytes(72) + struct.pack('<QQH', *older) + struct.pack('<QQH', *newer)
    return bytes(d + struct.pack('<HH', 1, len(conf)) + conf)


def token(m, owner, amount, t22=False):
    d = bytearray(165); d[:32] = bytes(m); d[32:64] = bytes(owner)
    struct.pack_into('<Q', d, 64, amount); d[108] = 1
    if t22:
        return bytes(d) + bytes([2]) + struct.pack('<HH', 7, 0) + struct.pack('<HHQ', 2, 8, 0)
    return bytes(d)


def global_config(p):
    d = bytearray(949); d[:8] = GLOBAL_DISC; d[8:40] = bytes([5]) * 32
    struct.pack_into('<QQ', d, 40, 20, 5)
    d[56] = p['disable_flags']
    for i, k in enumerate(RECIPIENTS):
        d[57 + 32 * i:89 + 32 * i] = bytes(k)
    d[353:385] = bytes(p['whitelist'])
    d[385:417] = bytes(RESERVED)
    for i, k in enumerate(RESERVED_LIST):
        d[418 + 32 * i:450 + 32 * i] = bytes(k)
    for i, k in enumerate(BUYBACK):
        d[643 + 32 * i:675 + 32 * i] = bytes(k)
    struct.pack_into('<Q', d, 899, p['buyback_bps'])
    d[940] = p['configurable']
    struct.pack_into('<Q', d, 941, 10000)
    return bytes(d)


def pool(p, creator, bump):
    d = bytearray(287); d[:8] = POOL_DISC; d[8] = bump
    struct.pack_into('<H', d, 9, INDEX)
    for off, k in [(11, creator), (43, BASE), (75, QUOTE), (107, LP), (139, VBASE), (171, VQUOTE), (211, p['cc'])]:
        d[off:off + 32] = bytes(k)
    struct.pack_into('<Q', d, 203, 10**9)
    d[243] = p['mayhem']; d[244] = p['cashback']
    d[245:261] = p['vqr'].to_bytes(16, 'little', signed=True)
    struct.pack_into('<Q', d, 261, p['pool_creator_bps'])
    struct.pack_into('<QQ', d, 271, p['pf'], p['cf'])
    return bytes(d[:p['pool_len']])


def fee_config(p):
    d = disc('account:FeeConfig') + bytes([FEE_BUMP]) + bytes([93]) * 32 + struct.pack('<QQQ', *p['fees'][:3])
    d += struct.pack('<I', 0) + struct.pack('<I', 0) + bytes(24)
    return d.ljust(4097, b'\0')


def gva():
    d = bytearray(544); d[:8] = disc('account:GlobalVolumeAccumulator')
    struct.pack_into('<qqq', d, 8, 0, 2**40, 86400)
    return bytes(d)


def uva(user=USER.pubkey()):
    d = bytearray(137); d[:8] = disc('account:UserVolumeAccumulator'); d[8:40] = bytes(user)
    return bytes(d)


def insn(op, dst=0, src=0, off=0, imm=0):
    return struct.pack('<BBhi', op, dst | (src << 4), off, imm)


def fee_stub(lp_bps, protocol_bps, creator_bps):
    for v in (lp_bps, protocol_bps, creator_bps):
        assert 0 <= v < 2**31
    text = b''.join([
        insn(0x7a, 10, 0, -24, lp_bps),        # stdw [r10-24], lp
        insn(0x7a, 10, 0, -16, protocol_bps),  # stdw [r10-16], protocol
        insn(0x7a, 10, 0, -8, creator_bps),    # stdw [r10-8], creator
        insn(0xbf, 1, 10),                     # mov64 r1, r10
        insn(0x07, 1, 0, 0, -24),              # add64 r1, -24
        insn(0xb7, 2, 0, 0, 24),               # mov64 r2, 24
        insn(0x85, 0, 0, 0, -1),               # call sol_set_return_data (R_BPF_64_32)
        insn(0xb7, 0, 0, 0, 0),                # mov64 r0, 0
        insn(0x95),                            # exit
    ])
    return _elf(text, call_offset=6 * 8)


def _elf(text, call_offset):
    # Layout: ehdr | phdr(PT_DYNAMIC) | .text | .dynamic | .dynsym | .dynstr | .rel.dyn | .shstrtab | shdrs
    # Virtual addresses equal file offsets.
    shnames = [b'', b'.text', b'.dynamic', b'.dynsym', b'.dynstr', b'.rel.dyn', b'.shstrtab']
    shstr = b'\0'.join(shnames) + b'\0'
    name_off = [0]
    for n in shnames[1:]:
        name_off.append(name_off[-1] + len(shnames[len(name_off) - 1]) + 1)
    dynstr = b'\0sol_set_return_data\0'
    dynsym = bytes(24) + struct.pack('<IBBHQQ', 1, 0x10, 0, 0, 0, 0)
    text_off = 64 + 56
    dyn_off = text_off + len(text)
    ndyn = 7
    sym_off = dyn_off + 16 * ndyn
    str_off = sym_off + len(dynsym)
    rel_off = (str_off + len(dynstr) + 7) & ~7
    shs_off = rel_off + 16
    sh_off = (shs_off + len(shstr) + 7) & ~7
    rel = struct.pack('<QQ', text_off + call_offset, (1 << 32) | 10)
    dynamic = b''.join(struct.pack('<QQ', t, v) for t, v in [
        (17, rel_off), (18, 16), (19, 16), (6, sym_off), (5, str_off), (10, len(dynstr)), (0, 0)])
    ehdr = b'\x7fELF' + bytes([2, 1, 1, 0]) + bytes(8)
    ehdr += struct.pack('<HHIQQQIHHHHHH', 3, 247, 1, text_off, 64, sh_off, 0, 64, 56, 1, 64, 7, 6)
    phdr = struct.pack('<IIQQQQQQ', 2, 6, dyn_off, dyn_off, dyn_off, len(dynamic), len(dynamic), 8)
    body = ehdr + phdr + text + dynamic + dynsym + dynstr
    body += bytes(rel_off - len(body)) + rel + shstr
    body += bytes(sh_off - len(body))

    def sh(i, typ, flags, off, size, link=0, info=0, align=1, entsize=0):
        return struct.pack('<IIQQQQIIQQ', name_off[i], typ, flags, off, off, size, link, info, align, entsize)
    return body + bytes(64) + sh(1, 1, 6, text_off, len(text), align=8) \
        + sh(2, 6, 3, dyn_off, len(dynamic), link=4, align=8, entsize=16) \
        + sh(3, 11, 2, sym_off, len(dynsym), link=4, info=1, align=8, entsize=24) \
        + sh(4, 3, 2, str_off, len(dynstr)) \
        + sh(5, 9, 2, rel_off, 16, link=3, align=8, entsize=16) \
        + struct.pack('<IIQQQQIIQQ', name_off[6], 3, 0, 0, shs_off, len(shstr), 0, 0, 1, 0)


DEFAULT = dict(ix='buy', amount=10**9, limit=10**12, track=None, fees=(20, 5, 30), vbase=10**12, vquote=10**10,
               ubase=10**10, uquote=10**11, vqr=0, pf=0, cf=0, mayhem=0, cashback=0, cc=COIN_CREATOR,
               pool_creator_bps=0, configurable=0, disable_flags=0, buyback_bps=2000, whitelist=Pubkey.default(),
               recipient=RECIPIENTS[0], pool_len=287, supply=10**15, tf=None, epoch=0, creator=CREATOR,
               rem=None, drop_rem=(), readonly_rem=(), bb_exists=True, recipient_ata_exists=True,
               vault_ata_exists=True, uva_state='absent', pool_v2_key=POOL_V2, bb_owner=BUYBACK[0], cata_key=None)


def remaining(p, q_prog):
    """Fixed remaining-account layout for the case, by symbolic name."""
    if p['rem'] is not None:
        names = list(p['rem'])
    else:
        bps = p['pool_creator_bps'] if p['configurable'] and p['pool_creator_bps'] else p['fees'][2]
        creator = p['cc'] != Pubkey.default() and bps > 0 and p['whitelist'] != USER.pubkey()
        names = []
        if creator:
            if p['cashback']:
                names += ['cata', 'uva', 'pv2'] if p['ix'] == 'sell' else ['cata', 'pv2']
            else:
                names += ['pv2']
        names += ['bbo', 'bba']
    keys = {'pv2': (p['pool_v2_key'], False), 'bbo': (p['bb_owner'], False),
            'bba': (ata(p['bb_owner'], QUOTE, q_prog), True), 'uva': (UVA, True),
            'cata': (p['cata_key'] or ata(UVA, QUOTE, q_prog), True), 'stranger': (STRANGER, False)}
    out = []
    for n in names:
        if n in p['drop_rem']:
            continue
        k, w = keys[n]
        out.append(AccountMeta(k, False, w and n not in p['readonly_rem']))
    return out


def instruction(p, poolk, q_prog, rata, vata, vauth):
    u = USER.pubkey()
    args = struct.pack('<QQ', p['amount'], p['limit'])
    if p['track'] is not None:
        args += bytes([p['track']])
    data = disc('global:' + p['ix']) + args
    m = [(poolk, False, True), (u, True, True), (CONFIG, False, False), (BASE, False, False), (QUOTE, False, False),
         (UBASE, False, True), (UQUOTE, False, True), (VBASE, False, True), (VQUOTE, False, True),
         (p['recipient'], False, False), (rata, False, True), (TOKEN, False, False), (q_prog, False, False),
         (SYSTEM, False, False), (ATA, False, False), (EVENT, False, False), (PROGRAM, False, False),
         (vata, False, True), (vauth, False, False)]
    if p['ix'] != 'sell':
        m += [(GVA, False, False), (UVA, False, True)]
    m += [(FEE_CONFIG, False, False), (FEE_PROGRAM, False, False)]
    metas = [AccountMeta(k, s, w) for k, s, w in m] + remaining(p, q_prog)
    return Instruction(PROGRAM, data, metas)


def run_case(p, image, inline=False):
    vm = LiteSVM().with_transaction_history(0)
    # Upgradeable layout (program account + programdata), as on mainnet: the program account is passed
    # to the fee CPI, and CPI charges data_len/250, so an ELF stored in that account would bill its size.
    elf = image if isinstance(image, bytes) else pathlib.Path(image).read_bytes()
    programdata = Pubkey.find_program_address([bytes(PROGRAM)], UPGRADEABLE)[0]
    if inline:
        vm.add_program(PROGRAM, elf)
    else:
        vm.set_account(programdata, Account(10**10, struct.pack('<IQB', 3, 0, 0) + bytes(32) + elf, UPGRADEABLE, False))
        vm.set_account(PROGRAM, Account(10**9, struct.pack('<I', 2) + bytes(programdata), UPGRADEABLE, True))
    vm.add_program(FEE_PROGRAM, fee_stub(*p['fees']))
    vm.set_clock(Clock(100, 1234567890, p['epoch'], 0, 1234567890))
    vm.airdrop(USER.pubkey(), 10**12)
    t22 = p['tf'] is not None
    q_prog = TOKEN22 if t22 else TOKEN
    poolk, bump = pool_key(p['creator'])
    vauth = creator_vault(p['cc'])
    rata = ata(p['recipient'], QUOTE, q_prog)
    vata = ata(vauth, QUOTE, q_prog)
    bba = ata(p['bb_owner'], QUOTE, q_prog)
    vm.set_account(EVENT, Account(10**9, b'', Pubkey.default()))
    vm.set_account(CONFIG, Account(10**9, global_config(p), PROGRAM))
    vm.set_account(poolk, Account(10**7, pool(p, p['creator'], bump), PROGRAM))
    vm.set_account(FEE_CONFIG, Account(10**9, fee_config(p), FEE_PROGRAM))
    vm.set_account(GVA, Account(10**9, gva(), PROGRAM))
    if p['uva_state'] == 'existing':
        vm.set_account(UVA, Account(10**8, uva(), PROGRAM))
    elif p['uva_state'] == 'bad-disc':
        vm.set_account(UVA, Account(10**8, bytes(137), PROGRAM))
    elif p['uva_state'] == 'foreign-owner':
        vm.set_account(UVA, Account(10**8, uva(), TOKEN))
    vm.set_account(BASE, Account(10**9, mint(p['supply'], 6), TOKEN))
    mdata = mint(MAX, 9)
    if t22:
        mdata = tf_mint(mdata, *p['tf'])
    vm.set_account(QUOTE, Account(10**9, mdata, q_prog))
    vm.set_account(VBASE, Account(10**9, token(BASE, poolk, p['vbase']), TOKEN))
    vm.set_account(UBASE, Account(10**9, token(BASE, USER.pubkey(), p['ubase']), TOKEN))
    vm.set_account(VQUOTE, Account(10**9, token(QUOTE, poolk, p['vquote'], t22), q_prog))
    vm.set_account(UQUOTE, Account(10**9, token(QUOTE, USER.pubkey(), p['uquote'], t22), q_prog))
    if p['recipient_ata_exists']:
        vm.set_account(rata, Account(10**9, token(QUOTE, p['recipient'], 7, t22), q_prog))
    if p['vault_ata_exists']:
        vm.set_account(vata, Account(10**9, token(QUOTE, vauth, 7, t22), q_prog))
    if p['bb_exists']:
        vm.set_account(bba, Account(10**9, token(QUOTE, p['bb_owner'], 7, t22), q_prog))
    ix = instruction(p, poolk, q_prog, rata, vata, vauth)
    tx = Transaction.new_signed_with_payer([set_compute_unit_limit(1_400_000), ix], USER.pubkey(), [USER],
                                           vm.latest_blockhash())
    r = vm.send_transaction(tx)
    failed = isinstance(r, FailedTransactionMetadata)
    meta = r.meta() if failed else r
    cu = meta.compute_units_consumed
    cu = cu() if callable(cu) else cu
    state = {}
    pa = vm.get_account(poolk)
    state['pool'] = bytes(pa.data).hex(); state['pool_lamports'] = str(pa.lamports)
    ua = vm.get_account(UVA)
    state['uva'] = None if ua is None else bytes(ua.data).hex()
    state['uva_lamports'] = None if ua is None else str(ua.lamports)
    for role, k in (('vault_base', VBASE), ('vault_quote', VQUOTE), ('user_base', UBASE), ('user_quote', UQUOTE),
                    ('recipient_ata', rata), ('creator_vault_ata', vata), ('buyback_ata', bba),
                    ('cashback_ata', ata(UVA, QUOTE, q_prog))):
        acc = vm.get_account(k)
        state[role] = None if acc is None or len(bytes(acc.data)) < 72 else str(struct.unpack_from('<Q', bytes(acc.data), 64)[0])
    state['user_lamports'] = str(vm.get_account(USER.pubkey()).lamports)
    return {'error': str(r.err()) if failed else None, 'cu': cu, 'logs': list(meta.logs()), 'state': state}


def anchor_code(logs):
    for line in logs:
        if 'Error Code: ' in line:
            return line.split('Error Code: ')[1].split('.')[0]
        if 'panicked' in line:
            return 'panic'
    return None


def program_logs(logs):
    return [l for l in logs if not ('consumed' in l and 'compute units' in l)]


PREFIX = b'programs/pump-amm/'


def elf_sections(blob):
    shoff, = struct.unpack_from('<Q', blob, 0x28)
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', blob, 0x3a)
    hs = [struct.unpack_from('<IIQQQQIIQQ', blob, shoff + i * shentsize) for i in range(shnum)]
    st = hs[shstrndx]; names = blob[st[4]:st[4] + st[5]]
    return {names[h[0]:names.index(b'\0', h[0])].decode(): (h[4], h[5]) for h in hs if h[0]}


def strip_prefix(blob):
    """Control image: the original with every reference to a 'programs/pump-amm/src/*.rs' string
    moved 18 bytes later (past the prefix) and the matching length immediate lowered by 18,
    so its AnchorError file names read 'src/...' like the rebuild's; panic Location records get the
    same move. Nothing else changes."""
    b = bytearray(blob)
    secs = elf_sections(bytes(b))
    ro_off, ro_len = secs['.rodata']; tx_off, tx_len = secs['.text']
    starts = {}
    for m in re.finditer(re.escape(PREFIX) + rb'src/[A-Za-z0-9_/]+\.rs', bytes(b[ro_off:ro_off + ro_len])):
        starts[ro_off + m.start()] = len(m.group(0))
    sites = 0
    for i in range(tx_off, tx_off + tx_len - 16, 8):
        if b[i] != 0x18:
            continue
        imm = struct.unpack_from('<I', b, i + 4)[0] | (struct.unpack_from('<I', b, i + 12)[0] << 32)
        if imm not in starts:
            continue
        n = starts[imm]
        for j in range(i + 16, i + 16 + 8 * 12, 8):
            if b[j] in (0x7a, 0x62, 0xb7, 0xb4) and struct.unpack_from('<i', b, j + 4)[0] == n:
                struct.pack_into('<i', b, j + 4, n - len(PREFIX))
                new = imm + len(PREFIX)
                struct.pack_into('<I', b, i + 4, new & 0xffffffff); struct.pack_into('<I', b, i + 12, new >> 32)
                sites += 1
                break
    # panic Location records are data, not code immediates: (u32 0, u32 file vaddr, u64 file len) in the ELF
    locations = 0
    for addr, n in starts.items():
        old = struct.pack('<IIQ', 0, addr, n)
        new = struct.pack('<IIQ', 0, addr + len(PREFIX), n - len(PREFIX))
        at = b.find(old)
        while at != -1:
            b[at:at + 16] = new
            locations += 1
            at = b.find(old, at + 16)
    return bytes(b), sites, locations


def jsonable(v):
    if isinstance(v, Pubkey):
        return str(v)
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, int) and not isinstance(v, bool) and abs(v) >= 2**53:
        return str(v)
    return v


def observed(p, rec):
    s = rec['state']
    pd = bytes.fromhex(s['pool'])
    def delta(role, start):
        return None if s[role] is None else str(int(s[role]) - start)
    o = {'pool_len': len(pd), 'user_base_delta': delta('user_base', p['ubase']),
         'user_quote_delta': delta('user_quote', p['uquote']), 'vault_base_delta': delta('vault_base', p['vbase']),
         'vault_quote_delta': delta('vault_quote', p['vquote']),
         'recipient_delta': delta('recipient_ata', 7 if p['recipient_ata_exists'] else 0),
         'creator_vault_delta': delta('creator_vault_ata', 7 if p['vault_ata_exists'] else 0),
         'buyback_delta': delta('buyback_ata', 7 if p['bb_exists'] else 0),
         'cashback_ata': s['cashback_ata']}
    return o


def produce(images):
    stripped = strip_prefix(pathlib.Path(images['original']).read_bytes())[0]
    rows = []
    for p in cases():
        rec = {'case': p['name'], 'group': p['group'], 'instruction': p['ix'],
               'params': {k: jsonable(v) for k, v in p.items() if k not in ('name', 'group', 'ix')}}
        for tag in ('original', 'candidate'):
            rec[tag] = run_case(p, images[tag])
        s = run_case(p, stripped)
        o, c = rec['original'], rec['candidate']
        rec['stripped_original'] = {'cu': s['cu'], 'same_error_state_as_candidate': (s['error'], s['state']) == (c['error'], c['state']),
                                    'same_logs_as_candidate': s['logs'] == c['logs']}
        rec['same_error'] = o['error'] == c['error']
        rec['same_state'] = o['state'] == c['state']
        rec['same_logs_ex_cu'] = program_logs(o['logs']) == program_logs(c['logs'])
        rec['same_logs'] = o['logs'] == c['logs']
        norm = lambda logs: [l.replace(' programs/pump-amm/src/', ' src/') for l in program_logs(logs)]
        rec['same_logs_path_normalized'] = norm(o['logs']) == norm(c['logs'])
        rec['cu_delta'] = c['cu'] - o['cu']
        rec['anchor_error'] = {'original': anchor_code(o['logs']), 'candidate': anchor_code(c['logs'])}
        rec['error_site'] = {t: next((l.split('AnchorError thrown in ')[1].split('. Error Code')[0]
                                      for l in rec[t]['logs'] if 'AnchorError thrown in ' in l), None)
                             for t in ('original', 'candidate')}
        rec['observed'] = observed(p, o)
        rows.append(rec)
    return rows


def sha_file(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def anchor_log_capacity(blob):
    """Literal pieces of the 'AnchorError thrown in ...' format string, read from the image's
    fmt::Arguments piece table, and fmt::Arguments::estimated_capacity (2 x their total length)."""
    at = blob.find(b'AnchorError thrown in ')
    rec = blob.find(struct.pack('<IIQ', 0, at, 22))
    pieces = []
    for k in range(6):
        _, addr, n = struct.unpack_from('<IIQ', blob, rec + 16 * k)
        pieces.append(blob[addr:addr + n].decode())
    return pieces, 2 * sum(len(x) for x in pieces)


def anchor_log_len(logs):
    line = next((l for l in logs if 'AnchorError thrown in ' in l), None)
    return None if line is None else len(line.encode()) - len('Program log: ')


def capacity_model(images, rows):
    """Rule: the rebuild's path is 18 bytes shorter (-18 from sol_log), and it skips one String growth
    (-104 more) when its message fits the initial capacity while the original's does not."""
    caps = {t: anchor_log_capacity(pathlib.Path(images[t]).read_bytes()) for t in ('original', 'candidate')}
    cap = caps['original'][1]
    table, match, total = {}, 0, 0
    for r in rows:
        lo, lc = anchor_log_len(r['original']['logs']), anchor_log_len(r['candidate']['logs'])
        if lo is None:
            continue
        predicted = -122 if lc <= cap < lo else -18
        total += 1
        match += predicted == r['cu_delta']
        k = (lc, lo, r['cu_delta'], predicted)
        table[k] = table.get(k, 0) + 1
    return {'pieces_original': caps['original'][0], 'pieces_candidate': caps['candidate'][0],
            'capacity_original': cap, 'capacity_candidate': caps['candidate'][1],
            'anchor_error_cases': total, 'rule_matches': match,
            'table': [{'rebuild_len': k[0], 'original_len': k[1], 'cu_delta': k[2], 'predicted': k[3], 'cases': v}
                      for k, v in sorted(table.items())]}


def inline_layout_control(images):
    """One nominal sell with the ELF stored in the program account (LiteSVM add_program) instead of programdata."""
    p = dict(DEFAULT); p.update(ix='sell', limit=1)
    o, c = run_case(p, images['original'], inline=True), run_case(p, images['candidate'], inline=True)
    so, sc = [pathlib.Path(images[t]).stat().st_size for t in ('original', 'candidate')]
    return {'cu_original': o['cu'], 'cu_candidate': c['cu'], 'cu_gap': o['cu'] - c['cu'],
            'elf_bytes_original': so, 'elf_bytes_candidate': sc, 'size_gap_div_250': (so - sc) // 250}


def summarize(images, rows, body):
    st = strip_prefix(pathlib.Path(images['original']).read_bytes())
    return {
        'inline_layout_control': inline_layout_control(images),
        'anchor_log_capacity_model': capacity_model(images, rows),
        'image_sha256': {k: sha_file(v) for k, v in images.items()},
        'case_count': len(rows),
        'success_count': sum(r['original']['error'] is None for r in rows),
        'behavior_match': sum(r['same_error'] and r['same_state'] for r in rows),
        'log_match_ex_cu': sum(r['same_logs_ex_cu'] for r in rows),
        'log_match_exact': sum(r['same_logs'] for r in rows),
        'log_match_path_normalized': sum(r['same_logs_path_normalized'] for r in rows),
        'cu_delta_histogram': {str(d): sum(r['cu_delta'] == d for r in rows) for d in sorted({r['cu_delta'] for r in rows})},
        'cu_equal': sum(r['cu_delta'] == 0 for r in rows),
        'cases': [{'case': r['case'], 'group': r['group'], 'instruction': r['instruction'], 'error': r['original']['error'],
                   'anchor_error': r['anchor_error'], 'cu_original': r['original']['cu'],
                   'cu_candidate': r['candidate']['cu'], 'cu_delta': r['cu_delta'],
                   'same_error': r['same_error'], 'same_state': r['same_state'],
                   'same_logs_ex_cu': r['same_logs_ex_cu'], 'error_site': r['error_site'],
                   'observed': r['observed']} for r in rows],
        'receipts_sha256': hashlib.sha256(body).hexdigest(),
        'stripped_original_control': {
            'sites_patched': st[1], 'panic_locations_patched': st[2], 'sha256': hashlib.sha256(st[0]).hexdigest(),
            'cu_equal_to_candidate': sum(r['stripped_original']['cu'] == r['candidate']['cu'] for r in rows),
            'logs_equal_to_candidate': sum(r['stripped_original']['same_logs_as_candidate'] for r in rows),
            'error_state_equal_to_candidate': sum(r['stripped_original']['same_error_state_as_candidate'] for r in rows),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--images', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    images = json.loads(a.images)
    rows = produce(images)
    out = pathlib.Path(a.out) / 'runtime'
    out.mkdir(parents=True, exist_ok=True)
    body = ''.join(json.dumps(r, sort_keys=True, separators=(',', ':')) + '\n' for r in rows).encode()
    (out / 'receipts.jsonl.gz').write_bytes(gzip.compress(body, mtime=0))
    summary = summarize(images, rows, body)
    rep = json.dumps(summary, sort_keys=True, indent=1).encode()
    (out / 'report.json.gz').write_bytes(gzip.compress(rep, mtime=0))
    print(json.dumps({k: summary[k] for k in ('case_count', 'success_count', 'behavior_match', 'log_match_ex_cu',
                                              'log_match_exact', 'log_match_path_normalized', 'cu_equal',
                                              'cu_delta_histogram', 'stripped_original_control')}))


def ceil_div(a, b):
    return (a + b - 1) // b


def buy_total(out, b, q, fees):
    curve = ceil_div(q * out, b - out)
    return curve + sum(ceil_div(curve * f, 10000) for f in fees)


def exact_plan(spend, b, q, fees):
    """Independent model of buy_exact_quote_in without a transfer fee -> (curve, base_out)."""
    bps = sum(fees)
    est = spend * 10000 // (10000 + bps)
    total = est + sum(ceil_div(est * f, 10000) for f in fees)
    curve = est - max(0, total - spend)
    return curve, b * (curve - 1) // (q + curve - 1)


def sell_quote(a, b, q):
    return q * a // (b + a)


def sell_out(a, b, q, fees):
    quote = sell_quote(a, b, q)
    return quote - sum(ceil_div(quote * f, 10000) for f in fees)


def first_spend(pred, start=1, stop=1000000):
    return next(s for s in range(start, stop) if pred(s))


def overflow_spend(fees):
    """Largest spendable amount whose estimate plus ceiled fees exceeds u64."""
    bps = sum(fees)
    for s in range(MAX, MAX - 100000, -1):
        est = s * 10000 // (10000 + bps)
        if est + sum(ceil_div(est * f, 10000) for f in fees) > MAX:
            return s
    raise SystemExit('no overflow spend')


def cases():
    out = []
    def c(name, group, **kw):
        p = dict(DEFAULT); p.update(kw); p.update(name=name, group=group)
        out.append(p)
    B, Q, F = DEFAULT['vbase'], DEFAULT['vquote'], DEFAULT['fees']
    NOV2 = ('bbo', 'bba')
    # buy: curve and rounding
    total = buy_total(10**9, B, Q, F)
    c('b-nominal', 'buy-curve')
    c('b-limit-exact', 'buy-curve', limit=total)
    c('b-limit-minus-1', 'buy-curve', limit=total - 1)
    c('b-out-1-ceil', 'buy-curve', amount=1)
    c('b-out-reserve-minus-1', 'buy-curve', amount=B - 1, limit=MAX)
    c('b-out-eq-reserve', 'buy-curve', amount=B, limit=MAX)
    c('b-out-reserve-plus-1', 'buy-curve', amount=B + 1, limit=MAX)
    c('b-out-max', 'buy-curve', amount=MAX, limit=MAX)
    c('b-zero-out', 'buy-curve', amount=0)
    c('b-zero-limit', 'buy-curve', limit=0)
    c('b-empty-base-reserve', 'buy-curve', vbase=0, amount=1)
    c('b-q-zero-out-eq-reserve', 'buy-curve', vquote=0, amount=B)
    # buy: u64 / u128 overflow sites
    big = dict(vquote=MAX, uquote=MAX, vbase=4, amount=2, limit=MAX)
    c('b-sum-lp-overflow', 'buy-overflow', fees=(1, 0, 0), **big)
    c('b-sum-creator-overflow', 'buy-overflow', fees=(0, 0, 1), **big)
    c('b-sum-protocol-overflow', 'buy-overflow', fees=(0, 1, 0), rem=NOV2, **big)
    c('b-fee-truncation', 'buy-overflow', fees=(2**31 - 1, 0, 0), **big)
    c('b-curve-truncation', 'buy-overflow', vquote=MAX, uquote=MAX, vbase=10**6, amount=10**6 - 1, limit=MAX)
    # buy: reserve accounting
    c('b-accrued-eq-vault', 'buy-reserves', pf=Q, cf=0)
    c('b-accrued-exceeds-vault', 'buy-reserves', pf=Q, cf=1)
    c('b-accrued-sum-overflow', 'buy-reserves', pf=MAX, cf=1)
    c('b-vqr-neg-past-zero', 'buy-reserves', vqr=-Q - 1)
    c('b-vqr-pos-past-u64', 'buy-reserves', vqr=MAX - Q + 1)
    c('b-vqr-i128-overflow', 'buy-reserves', vqr=2**127 - 1)
    # buy_exact_quote_in: estimate and adjustment
    X = 'buy_exact_quote_in'
    spend = 10**9
    curve, base_out = exact_plan(spend, B, Q, F)
    c('x-nominal', 'exact-estimate', ix=X, amount=spend, limit=1)
    c('x-min-exact', 'exact-estimate', ix=X, amount=spend, limit=base_out)
    c('x-min-plus-1', 'exact-estimate', ix=X, amount=spend, limit=base_out + 1)
    c('x-spend-1-estimate-zero', 'exact-estimate', ix=X, amount=1, limit=1)
    c('x-spend-2-adjust-underflow', 'exact-estimate', ix=X, amount=2, limit=1)
    c('x-spend-3-curve-zero', 'exact-estimate', ix=X, amount=3, limit=1)
    c('x-spend-4-base-zero', 'exact-estimate', ix=X, amount=4, limit=1)
    fit = first_spend(lambda s: exact_plan(s, B, Q, F)[1] > 0)
    c('x-smallest-spend-with-base', 'exact-estimate', ix=X, amount=fit, limit=1)
    c('x-below-smallest-spend', 'exact-estimate', ix=X, amount=fit - 1, limit=1)
    c('x-zero-spend', 'exact-estimate', ix=X, amount=0, limit=1)
    c('x-zero-min', 'exact-estimate', ix=X, amount=spend, limit=0)
    c('x-all-fees-zero', 'exact-estimate', ix=X, amount=spend, limit=1, fees=(0, 0, 0), rem=NOV2)
    c('x-no-coin-creator', 'exact-estimate', ix=X, amount=spend, limit=1, cc=Pubkey.default())
    c('x-fee-100pct', 'exact-estimate', ix=X, amount=spend, limit=1, fees=(10000, 0, 0), rem=NOV2)
    bigf = (1, 1, 1)
    c('x-total-sum-overflow', 'exact-estimate', ix=X, amount=overflow_spend(bigf), limit=1, fees=bigf, uquote=MAX)
    c('x-spend-max', 'exact-estimate', ix=X, amount=MAX, limit=1, uquote=MAX)
    c('x-q-zero-curve-1', 'exact-estimate', ix=X, amount=4, limit=1, vquote=0)
    c('x-empty-base-reserve', 'exact-estimate', ix=X, amount=spend, limit=1, vbase=0)
    # sell: curve, fee subtraction and slippage
    S = 'sell'
    amt = 10**9
    u = sell_out(amt, B, Q, F)
    c('s-nominal', 'sell-curve', ix=S, limit=1)
    c('s-min-exact', 'sell-curve', ix=S, limit=u)
    c('s-min-plus-1', 'sell-curve', ix=S, limit=u + 1)
    c('s-zero-amount', 'sell-curve', ix=S, amount=0, limit=1)
    c('s-quote-floor-zero', 'sell-curve', ix=S, amount=1, limit=0, rem=NOV2)
    q1 = first_spend(lambda a: sell_quote(a, B, Q) == 1, 90)
    q3 = first_spend(lambda a: sell_quote(a, B, Q) == 3, 290)
    c('s-quote-1-fee-underflow', 'sell-curve', ix=S, amount=q1, limit=0)
    c('s-quote-3-user-zero', 'sell-curve', ix=S, amount=q3, limit=0)
    c('s-quote-3-min-1', 'sell-curve', ix=S, amount=q3, limit=1)
    c('s-lp-exceeds-quote', 'sell-curve', ix=S, limit=0, fees=(10001, 0, 0), rem=NOV2)
    c('s-creator-exceeds-quote', 'sell-curve', ix=S, limit=0, fees=(0, 0, 10001))
    c('s-protocol-exceeds-quote', 'sell-curve', ix=S, limit=0, fees=(0, 10001, 0), rem=NOV2)
    c('s-fee-truncation', 'sell-curve', ix=S, limit=0, fees=(2**31 - 1, 0, 0), vquote=MAX, vbase=1, amount=1)
    c('s-empty-base-reserve', 'sell-curve', ix=S, vbase=0, limit=0)
    # sell: real vs virtual reserves
    vq, vqr = 10**7, 10**10
    q = vq + vqr
    wo_lp = sell_quote(amt, B, q) - ceil_div(sell_quote(amt, B, q) * F[0], 10000)
    c('s-real-short', 'sell-reserves', ix=S, limit=0, vquote=wo_lp - 1, vqr=q - wo_lp + 1)
    c('s-real-exact', 'sell-reserves', ix=S, limit=0, vquote=wo_lp, vqr=q - wo_lp)
    c('s-real-accrued-short', 'sell-reserves', ix=S, limit=0, vquote=wo_lp, vqr=q - wo_lp, pf=1)
    c('s-accrued-exceeds-vault', 'sell-reserves', ix=S, limit=0, pf=Q + 1)
    c('s-vqr-neg-past-zero', 'sell-reserves', ix=S, limit=0, vqr=-Q - 1)
    # sell: Token-level failures after every program check
    c('s-user-short-of-base', 'sell-reserves', ix=S, limit=0, ubase=amt - 1)
    return out


if __name__ == '__main__':
    main()
