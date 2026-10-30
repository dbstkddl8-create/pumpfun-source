#!/usr/bin/env python3
"""Pump Main AnchorError log: why the rebuild gap is +14 at most sites and +118 at some.

The AnchorError line is built with format!(), so its String starts with capacity 2 x (literal piece
bytes) = 142 and reallocates when the message is longer. The original's file!() path is 14 bytes
longer than the rebuild's. This producer measures the message cost directly: it rewrites the single
`stdw [r10-560], <len>` immediate that holds the filename length at one error site, in memory only,
on both images, and runs the same failing instruction across lengths. No image file is written.

Fixtures are the synthetic sweep_creator_fee / sweep_protocol_fee states (upgradeable loader, Pump
image only, LiteSVM built-ins for everything else, fixed seeds and clock, no network). Replays need
only the two images; the merged-packet table additionally reads research/<packet>/runtime receipts.

Usage:
  python3 producer.py --root <repo> --images '{"original": "...", "candidate": "..."}' --out <packet dir>
"""
import argparse
import base64
import gzip
import hashlib
import json
import struct
from pathlib import Path

from solders.account import Account
from solders.clock import Clock
from solders.compute_budget import set_compute_unit_limit
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.litesvm import LiteSVM
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from solders.transaction_metadata import FailedTransactionMetadata

PROGRAM = Pubkey.from_string('6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P')
TOKEN = Pubkey.from_string('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA')
TOKEN22 = Pubkey.from_string('TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb')
ATA_PROGRAM = Pubkey.from_string('ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL')
WSOL = Pubkey.from_string('So11111111111111111111111111111111111111112')
SYSTEM = Pubkey.default()
UPGRADEABLE = Pubkey.from_string('BPFLoaderUpgradeab1e11111111111111111111111')
PAYER_SEED = bytes([239]) * 32
PAYER = Keypair.from_seed(PAYER_SEED).pubkey()
OTHER_SEED = bytes([238]) * 32
OTHER = Keypair.from_seed(OTHER_SEED).pubkey()
SIGNER_SEEDS = {str(PAYER): PAYER_SEED, str(OTHER): OTHER_SEED}
STRANGER = Pubkey(bytes([77]) * 32)
MINT = Pubkey(bytes([11]) * 32)
QUOTE = Pubkey(bytes([12]) * 32)
CREATOR = Pubkey(bytes([13]) * 32)
FEE_RECIPIENT = Pubkey(bytes([200]) * 32)
FEE_LIST = [Pubkey(bytes([20 + 10 * i]) * 32) for i in range(7)]  # sorted for binary_search
RESERVED = Pubkey(bytes([201]) * 32)
RESERVED_LIST = [Pubkey(bytes([120 + 5 * i]) * 32) for i in range(7)]
TS = 1_800_000_000
CU_LIMIT = 1_400_000

CREATOR_DISC = hashlib.sha256(b'global:sweep_creator_fee').digest()[:8]
PROTOCOL_DISC = hashlib.sha256(b'global:sweep_protocol_fee').digest()[:8]
EVENT_DISC = hashlib.sha256(b'event:SweepBondingCurveFeeEvent').digest()[:8]
GLOBAL_DISC = bytes([167, 232, 232, 177, 200, 108, 114, 127])
CURVE_DISC = bytes([23, 183, 248, 55, 96, 216, 172, 96])
CREATOR_FEE_OFF, PROTOCOL_FEE_OFF = 125, 133
RENT_0 = 890_880
RENT_166 = 2_046_240
RENT_MINT, RENT_TOKEN = 1_461_600, 2_039_280

pda = lambda seeds, program=PROGRAM: Pubkey.find_program_address(seeds, program)[0]
GLOBAL = pda([b'global'])
EVENT_AUTHORITY = pda([b'__event_authority'])
CURVE = pda([b'bonding-curve', bytes(MINT)])
VAULT = pda([b'creator-vault', bytes(CREATOR)])


def ata(owner, mint, program=TOKEN):
    return pda([bytes(owner), bytes(program), bytes(mint)], ATA_PROGRAM)


# ---- account data builders ----


def global_data(fee_list=FEE_LIST):
    d = bytearray(1088)
    d[:8] = GLOBAL_DISC
    d[8] = 1
    d[9:41] = bytes(Pubkey(bytes([91]) * 32))
    d[41:73] = bytes(FEE_RECIPIENT)
    struct.pack_into('<QQQQQ', d, 73, 1_073_000_000_000_000, 30_000_000_000, 793_100_000_000_000,
                     1_000_000_000_000_000, 95)
    struct.pack_into('<Q', d, 154, 30)
    for i, k in enumerate(fee_list):
        d[162 + 32 * i:194 + 32 * i] = bytes(k)
    d[450] = 1
    d[451:483] = bytes(Pubkey(bytes([92]) * 32))
    d[483:515] = bytes(RESERVED)
    d[515] = 1
    for i, k in enumerate(RESERVED_LIST):
        d[516 + 32 * i:548 + 32 * i] = bytes(k)
    return bytes(d)


def curve_data(quote_mint, creator_fee=12_345, protocol_fee=67_890, rqr=0, complete=0, mayhem=0, cashback=0,
               creator=CREATOR, length=166, holder=0):
    d = bytearray(max(166, length))
    d[:8] = CURVE_DISC
    struct.pack_into('<QQQQQ', d, 8, 1_073_000_000_000_000, 30_000_000_000, 793_100_000_000_000, rqr,
                     1_000_000_000_000_000)
    d[48] = complete
    d[49:81] = bytes(creator)
    d[81] = mayhem
    d[82] = cashback
    d[83:115] = bytes(quote_mint)
    d[124] = holder
    struct.pack_into('<QQ', d, CREATOR_FEE_OFF, creator_fee, protocol_fee)
    return bytes(d[:length])


def mint_data(decimals=6, supply=10**15):
    return struct.pack('<I32sQBBI32s', 0, bytes(32), supply, decimals, 1, 0, bytes(32))


def tf_mint(bps=100, maximum=2**64 - 1, decimals=6):
    fee = struct.pack('<QQH', 0, maximum, bps)
    body = bytes(32) + bytes(32) + struct.pack('<Q', 0) + fee + fee
    return mint_data(decimals) + bytes(83) + bytes([1]) + struct.pack('<HH', 1, 108) + body


def token_data(mint, owner, amount, state=1, tf=False, native=None):
    d = bytearray(165)
    d[:32] = bytes(mint)
    d[32:64] = bytes(owner)
    struct.pack_into('<Q', d, 64, amount)
    d[108] = state
    if native is not None:
        struct.pack_into('<IQ', d, 109, 1, native)
    if tf:
        d += bytes([2]) + struct.pack('<HHQ', 2, 8, 0)
    return bytes(d)


def acct(key, lamports, owner=SYSTEM, data=b''):
    return [str(key), lamports, str(owner), data.hex()]


# ---- plan: cases are pure data ----

MODES = {
    # mode: (curve quote_mint, quote_mint account, token program, mint data, token-account TLV)
    'native': (SYSTEM, WSOL, TOKEN, mint_data(9), False),
    'spl': (QUOTE, QUOTE, TOKEN, mint_data(6), False),
    'wsol': (WSOL, WSOL, TOKEN, mint_data(9), False),
    't22': (QUOTE, QUOTE, TOKEN22, mint_data(6), False),
    't22fee': (QUOTE, QUOTE, TOKEN22, tf_mint(100), True),
    't22fee-cap': (QUOTE, QUOTE, TOKEN22, tf_mint(1000, 50), True),
}


def metas(bucket='creator', mode='native', recipient=None, **over):
    _, quote, program, _, _ = MODES[mode]
    recipient = recipient if recipient is not None else (VAULT if bucket == 'creator' else FEE_RECIPIENT)
    order = [('payer', PAYER, True, True), ('global', GLOBAL, False, False), ('base_mint', MINT, False, False),
             ('quote_mint', quote, False, False), ('quote_token_program', program, False, False),
             ('associated_token_program', ATA_PROGRAM, False, False), ('system_program', SYSTEM, False, False),
             ('bonding_curve', CURVE, False, True),
             ('associated_quote_bonding_curve', ata(CURVE, quote, program), False, True),
             ('recipient', recipient, False, True),
             ('associated_quote_recipient', ata(recipient, quote, program), False, True),
             ('event_authority', EVENT_AUTHORITY, False, False), ('program', PROGRAM, False, False)]
    out = []
    for name, key, signer, writable in order:
        o = over.get(name, {})
        if o is None:
            continue
        out.append([str(o.get('key', key)), o.get('signer', signer), o.get('writable', writable)])
    return out


def ix(bucket='creator', mode='native', recipient=None, **over):
    disc = CREATOR_DISC if bucket == 'creator' else PROTOCOL_DISC
    return {'program': str(PROGRAM), 'data_hex': disc.hex(), 'metas': metas(bucket, mode, recipient, **over)}


def state(mode='native', bucket='creator', recipient=None, curve_lamports=None, recipient_lamports=10**9,
          source=10**9, dest=77, source_state=1, dest_state=1, glob=None, base=None, extra=(), rm=(), **curve):
    quote_key, quote, program, mdata, tf = MODES[mode]
    recipient = recipient if recipient is not None else (VAULT if bucket == 'creator' else FEE_RECIPIENT)
    cd = curve_data(quote_key, **curve)
    if curve_lamports is None:
        c = curve.get('creator_fee', 12_345)
        p = curve.get('protocol_fee', 67_890)
        curve_lamports = 10**9 + (c + p + curve.get('rqr', 0) if mode == 'native' else 0)
    a = [acct(GLOBAL, 10**9, PROGRAM, glob if glob is not None else global_data()),
         acct(MINT, RENT_MINT, *(base or (TOKEN, mint_data()))),
         acct(CURVE, curve_lamports, PROGRAM, cd)]
    if recipient != SYSTEM and recipient_lamports:
        a.append(acct(recipient, recipient_lamports))
    if mode != 'native':
        a.append(acct(quote, RENT_MINT, program, mdata))
        wrapped = quote == WSOL
        src, dst = ata(CURVE, quote, program), ata(recipient, quote, program)
        if source is not None:
            a.append(acct(src, RENT_TOKEN + (source if wrapped else 0), program,
                          token_data(quote, CURVE, source, source_state, tf, RENT_TOKEN if wrapped else None)))
        if dest is not None:
            a.append(acct(dst, RENT_TOKEN + (dest if wrapped else 0), program,
                          token_data(quote, recipient, dest, dest_state, tf, RENT_TOKEN if wrapped else None)))
    else:
        a.append(acct(WSOL, RENT_MINT, TOKEN, mdata))
    return [x for x in a if x[0] not in {str(k) for k in rm}] + list(extra)


def plan():
    cases = []

    def add(name, note, accounts=None, ins=None, bucket='creator', mode='native', recipient=None, ms=None, **st):
        accs = accounts if accounts is not None else state(mode, bucket, recipient, **st)
        i = ins if ins is not None else [ix(bucket, mode, recipient, **(ms or {}))]
        cases.append({'case': name, 'note': note, 'accounts': accs, 'instructions': i, 'unix_timestamp': TS})

    # -- native: both buckets, amounts, recipient rent --
    add('native-creator-ok', 'native curve, creator bucket, vault funded')
    add('native-protocol-ok', 'native curve, protocol bucket, Global.fee_recipient', bucket='protocol')
    add('native-creator-zero', 'creator_fee 0: "Nothing to sweep" return', creator_fee=0)
    add('native-protocol-zero', 'protocol_fees 0: "Nothing to sweep" return', bucket='protocol', protocol_fee=0)
    add('native-creator-1-lamport', 'creator_fee 1', creator_fee=1)
    add('native-protocol-1-lamport', 'protocol_fees 1', bucket='protocol', protocol_fee=1)
    add('native-creator-vault-absent', 'creator vault has no account: payer funds 890,880 rent, then the amount lands',
        recipient_lamports=0)
    add('native-creator-vault-rent-minus-1', 'vault at rent-1: 890,880 more from the payer, not 1',
        recipient_lamports=RENT_0 - 1)
    add('native-creator-vault-rent-exact', 'vault exactly at the 0-byte rent minimum: no payer transfer',
        recipient_lamports=RENT_0)
    add('native-protocol-recipient-absent-small', 'protocol bucket has no rent top-up: 67,890 into an empty recipient',
        bucket='protocol', recipient_lamports=0)
    add('native-protocol-recipient-absent-rent', 'protocol amount = 890,880 into an empty recipient',
        bucket='protocol', recipient_lamports=0, protocol_fee=RENT_0)
    # -- native: curve rent / reserved accounting before the sweep --
    res = 12_345 + 67_890
    add('curve-lamports-exact', 'curve lamports = reserved + rent: no top-up', curve_lamports=RENT_166 + res)
    add('curve-lamports-short-1', 'one lamport under reserved + rent: payer tops up 1', curve_lamports=RENT_166 + res - 1)
    add('curve-lamports-below-reserved', 'lamports below the reserved sum: payer tops up the whole rent',
        curve_lamports=res - 1)
    add('curve-lamports-with-rqr', 'real_quote_reserves 5e9 reserved too', rqr=5 * 10**9,
        curve_lamports=5 * 10**9 + res + RENT_166)
    add('curve-rqr-short-1', 'same with one lamport less', rqr=5 * 10**9, curve_lamports=5 * 10**9 + res + RENT_166 - 1)
    add('fee-sum-overflow', 'creator_fee u64::MAX + protocol_fees 1 overflows the reserved sum',
        creator_fee=2**64 - 1, protocol_fee=1, curve_lamports=10**9)
    add('reserves-sum-overflow', 'real_quote_reserves + fees overflows', rqr=2**64 - 1, curve_lamports=10**9)
    add('native-amount-above-lamports', 'native creator_fee 2^62 with 1e9 curve lamports: sub_lamports underflows',
        creator_fee=2**62, curve_lamports=10**9)
    # -- curve layouts --
    for n in (125, 133, 141, 150):
        add(f'layout-{n}', f'curve account of {n} bytes: realloc to 166, fee fields beyond the end read as 0',
            length=n, bucket='protocol' if n == 141 else 'creator')
    add('layout-250', 'curve account of 250 bytes: no realloc', length=250)
    add('flags-complete-cashback-holder', 'complete, cashback and holder-reward flags set: still sweeps',
        complete=1, cashback=1, holder=1)
    # -- recipients --
    add('recipient-default', 'recipient = default key', recipient=SYSTEM, rm=[SYSTEM])
    add('recipient-default-creator-default', 'creator = default and recipient = default', recipient=SYSTEM,
        creator=SYSTEM)
    add('creator-wrong-recipient', 'creator bucket, recipient = fee recipient', recipient=FEE_RECIPIENT)
    add('creator-default-vault', 'curve.creator = default: vault of the default key is accepted',
        creator=SYSTEM, recipient=pda([b'creator-vault', bytes(SYSTEM)]))
    add('protocol-unlisted', 'protocol bucket, recipient outside Global', bucket='protocol', recipient=STRANGER)
    for i in (0, 3, 6):
        add(f'protocol-list-{i}', f'protocol bucket, Global.fee_recipients[{i}]', bucket='protocol',
            recipient=FEE_LIST[i])
    add('protocol-reserved-non-mayhem', 'reserved recipient on a non-mayhem curve', bucket='protocol',
        recipient=RESERVED)
    add('mayhem-reserved', 'mayhem curve, Global.reserved_fee_recipient', bucket='protocol', recipient=RESERVED,
        mayhem=1)
    add('mayhem-reserved-list-6', 'mayhem curve, reserved_fee_recipients[6]', bucket='protocol',
        recipient=RESERVED_LIST[6], mayhem=1)
    add('mayhem-normal-recipient', 'mayhem curve, normal fee recipient', bucket='protocol', mayhem=1)
    g = bytearray(global_data())
    g[41:73] = bytes(CURVE)
    add('protocol-recipient-is-curve', 'Global.fee_recipient = the curve PDA: sub + add on the same account',
        accounts=state('native', 'protocol', CURVE, recipient_lamports=0, glob=bytes(g)),
        bucket='protocol', recipient=CURVE)
    g = bytearray(global_data())
    g[41:73] = bytes(PAYER)
    add('protocol-recipient-is-payer', 'Global.fee_recipient = fee payer',
        accounts=state('native', 'protocol', PAYER, recipient_lamports=0, glob=bytes(g)),
        bucket='protocol', recipient=PAYER)
    # -- sequences --
    add('seq-both-buckets', 'creator then protocol in one transaction',
        ins=[ix('creator'), ix('protocol')], recipient=None,
        extra=[acct(FEE_RECIPIENT, 10**9)])
    add('seq-repeat-creator', 'creator bucket twice in one transaction: second is "Nothing to sweep"',
        ins=[ix('creator'), ix('creator')])
    # -- token quote --
    add('spl-creator-ok', 'SPL quote, creator bucket', mode='spl')
    add('spl-protocol-ok', 'SPL quote, protocol bucket', mode='spl', bucket='protocol')
    add('spl-dest-created', 'recipient ATA absent: created from the payer', mode='spl', dest=None)
    add('spl-source-missing', 'curve ATA absent', mode='spl', source=None)
    add('spl-source-missing-zero', 'curve ATA absent, bucket 0: returns before ATA admission', mode='spl',
        source=None, dest=None, creator_fee=0)
    add('spl-source-exact', 'curve ATA balance = amount', mode='spl', source=12_345)
    add('spl-source-short-1', 'curve ATA balance = amount - 1', mode='spl', source=12_344)
    add('spl-source-wrong-owner', 'curve ATA token owner field = another key (first admit_associated_token_account)',
        mode='spl', extra=[acct(ata(CURVE, QUOTE), RENT_TOKEN, TOKEN, token_data(QUOTE, STRANGER, 10**9))])
    add('spl-dest-wrong-owner', 'recipient ATA token owner field = another key (second admit_associated_token_account)',
        mode='spl', extra=[acct(ata(VAULT, QUOTE), RENT_TOKEN, TOKEN, token_data(QUOTE, STRANGER, 77))])
    add('spl-source-foreign-owner', 'curve ATA owned by another program: 6010 in the first admission',
        mode='spl', extra=[acct(ata(CURVE, QUOTE), RENT_TOKEN, STRANGER, token_data(QUOTE, CURVE, 10**9))])
    add('spl-dest-foreign-owner', 'recipient ATA owned by another program: 6010 in the second admission',
        mode='spl', extra=[acct(ata(VAULT, QUOTE), RENT_TOKEN, STRANGER, token_data(QUOTE, VAULT, 77))])
    add('spl-source-frozen', 'curve ATA frozen', mode='spl', source_state=2)
    add('spl-dest-frozen', 'recipient ATA frozen', mode='spl', dest_state=2)
    add('spl-recipient-absent-lamports', 'creator vault with no lamports in the token branch: no vault rent top-up',
        mode='spl', recipient_lamports=0)
    add('wsol-curve', 'curve quote = WSOL: token branch, not native', mode='wsol')
    add('t22-creator-ok', 'Token-2022 quote, no extensions', mode='t22')
    add('t22-fee-100bps', 'TransferFee 1%: recipient receives net of the withheld fee', mode='t22fee')
    add('t22-fee-cap', 'TransferFee 10% with max fee 50', mode='t22fee-cap')
    add('t22-fee-dest-created', 'recipient ATA created under a TransferFee mint', mode='t22fee', dest=None)
    # -- mints --
    add('base-mint-token-2022', 'base mint owned by Token-2022', base=(TOKEN22, mint_data()))
    add('quote-mismatch', 'SPL curve quote, quote_mint slot = another mint with valid ATAs',
        accounts=state('spl') + [acct(STRANGER, RENT_MINT, TOKEN, mint_data())],
        ins=[ix('creator', 'spl', quote_mint={'key': STRANGER},
                associated_quote_bonding_curve={'key': ata(CURVE, STRANGER)},
                associated_quote_recipient={'key': ata(VAULT, STRANGER)})])
    return cases


# Same paths as neighbouring cases; dropped to stay at 60.
DROPPED = {'recipient-default-creator-default', 'native-protocol-recipient-absent-rent'}


# ---- execution (verify.py imports this from the packet copy) ----

LOADERS = ('upgradeable',)


def load_vm(image):
    vm = LiteSVM().with_transaction_history(0).with_sigverify(False)
    elf = Path(image).read_bytes()
    programdata = Pubkey.find_program_address([bytes(PROGRAM)], UPGRADEABLE)[0]
    vm.set_account(programdata, Account(10**10, struct.pack('<IQB', 3, 0, 0) + bytes(32) + elf, UPGRADEABLE, False))
    vm.set_account(PROGRAM, Account(10**9, struct.pack('<I', 2) + bytes(programdata), UPGRADEABLE, True))
    vm.airdrop(PAYER, 10**11)
    return vm


FIXED = {PROGRAM, TOKEN, TOKEN22, ATA_PROGRAM, SYSTEM, PAYER}
PANIC = 'Program log: panicked at '


def pump_messages(logs):
    """`msg!` lines logged while the Pump program itself is on top of the invoke stack."""
    stack, out = [], []
    for l in logs:
        parts = l.split(' ')
        if len(parts) == 4 and parts[0] == 'Program' and parts[2] == 'invoke':
            stack.append(parts[1])
        elif len(parts) >= 3 and parts[0] == 'Program' and parts[2] in ('success', 'failed:') and stack:
            stack.pop()
        elif (stack and stack[-1] == str(PROGRAM) and l.startswith('Program log: ')
              and not l.startswith('Program log: Instruction: ') and not l.startswith('Program log: AnchorError')
              and not l.startswith(PANIC)):
            out.append(l[13:])
    return out


def run_case(vm, index, c):
    vm.expire_blockhash()
    vm.set_clock(Clock(1000 + index, TS, 0, 0, c['unix_timestamp']))
    keys = set()
    for k, lam, owner, data in c['accounts']:
        key = Pubkey.from_string(k)
        keys.add(key)
        vm.set_account(key, Account(lam, bytes.fromhex(data), Pubkey.from_string(owner)))
    ixs = [set_compute_unit_limit(CU_LIMIT)]
    for i in c['instructions']:
        ms = [AccountMeta(Pubkey.from_string(k), s, w) for k, s, w in i['metas']]
        keys |= {m.pubkey for m in ms}
        ixs.append(Instruction(Pubkey.from_string(i['program']), bytes.fromhex(i['data_hex']), ms))
    payer = Keypair.from_seed(PAYER_SEED)
    blockhash = vm.latest_blockhash()
    tx = Transaction.new_unsigned(Message.new_with_blockhash(ixs, payer.pubkey(), blockhash))
    signers = sorted({m[0] for i in c['instructions'] for m in i['metas'] if m[1] and m[0] in SIGNER_SEEDS} - {str(PAYER)})
    tx.partial_sign([payer] + [Keypair.from_seed(SIGNER_SEEDS[k]) for k in signers], blockhash)
    result = vm.send_transaction(tx)
    failed = isinstance(result, FailedTransactionMetadata)
    meta = result.meta() if failed else result
    logs = list(meta.logs())
    after = {}
    for key in sorted(keys - FIXED, key=str):
        a = vm.get_account(key)
        if a is not None and (a.lamports or a.data) and not a.executable:
            after[str(key)] = [a.lamports, str(a.owner), a.executable, bytes(a.data).hex()]
    payer_after = vm.get_account(PAYER).lamports
    for key in keys - FIXED:  # reset so the next case starts from its own state only
        a = vm.get_account(key)
        if a is not None and not a.executable:
            vm.set_account(key, Account(0, b'', SYSTEM))
    vm.set_account(PAYER, Account(10**11, b'', SYSTEM))
    return {'case': c['case'],
            'transaction_base64': base64.b64encode(bytes(tx)).decode(),
            'error': str(result.err()) if failed else None,
            'events': [l[14:] for l in logs if l.startswith('Program data: ')],
            'handler_messages': pump_messages(logs),
            'panic_messages': [l[len(PANIC):].split(':', 3)[-1] for l in logs if l.startswith(PANIC)],
            'inner_instructions': json.loads(meta.to_json())['inner_instructions'],
            'accounts_after': after, 'payer_lamports_after': payer_after, 'compute_units': meta.compute_units_consumed(), 'logs': logs}


def run_plan(image, loader, cases):
    assert loader == 'upgradeable'
    vm = load_vm(image)
    return [run_case(vm, i, c) for i, c in enumerate(cases)]


BEHAVIOR = ('transaction_base64', 'error', 'events', 'handler_messages', 'panic_messages', 'inner_instructions',
            'accounts_after', 'payer_lamports_after')
SITE = 'Program log: AnchorError thrown in '
SITE2 = 'Program log: AnchorError caused by account: '


def classify_logs(original, candidate):
    if len(original) != len(candidate):
        return [{'kind': 'line-count', 'original': len(original), 'candidate': len(candidate)}]
    out = []
    for a, b in zip(original, candidate):
        if a == b:
            continue
        if a.startswith(SITE) and b.startswith(SITE) and a.split('. ', 1)[1:] == b.split('. ', 1)[1:]:
            out.append({'kind': 'anchor-error-site', 'original': a[len(SITE):].split('. ')[0],
                        'candidate': b[len(SITE):].split('. ')[0]})
        elif a.startswith(PANIC) and b.startswith(PANIC):
            out.append({'kind': 'panic-site', 'original': a[len(PANIC):], 'candidate': b[len(PANIC):]})
        elif ' consumed ' in a and ' consumed ' in b:
            out.append({'kind': 'consumed', 'original': a, 'candidate': b})
        else:
            out.append({'kind': 'other', 'original': a, 'candidate': b})
    return out


def outcome(r):
    if r['error']:
        for line in r['logs']:
            if 'Error Code: ' in line:
                code = line.split('Error Code: ', 1)[1].split('.', 1)[0]
                num = line.split('Error Number: ', 1)[1].split('.', 1)[0] if 'Error Number: ' in line else '?'
                return f'error:{num} {code}'
        if r['panic_messages']:
            return 'panic:' + r['panic_messages'][0].strip()
        return 'error:' + r['error']
    return 'ok'


def decode_event(b64):
    d = base64.b64decode(b64)
    if d[:8] != EVENT_DISC or len(d) < 8 + 8 + 32 * 4 + 8 + 1:
        return None
    ts, mint, curve, quote, recipient, amount, bucket = struct.unpack_from('<q32s32s32s32sQB', d, 8)
    return {'timestamp': ts, 'mint': str(Pubkey(mint)), 'bonding_curve': str(Pubkey(curve)),
            'quote_mint': str(Pubkey(quote)), 'recipient': str(Pubkey(recipient)), 'amount': amount, 'bucket': bucket}


def logged_compute_units(logs):
    """Sum of 'consumed N of' lines of top-level Pump invocations (LiteSVM's failed-transaction meta
    can report the whole budget, the log line keeps the real figure)."""
    depth, total = 0, 0
    for l in logs:
        parts = l.split(' ')
        if len(parts) == 4 and parts[0] == 'Program' and parts[2] == 'invoke':
            depth += 1
        elif len(parts) >= 3 and parts[0] == 'Program' and parts[2] in ('success', 'failed:'):
            depth -= 1
        elif depth == 1 and l.startswith(f'Program {PROGRAM} consumed '):
            total += int(parts[3])
    return total


def fee_fields(entry):
    """(data length, creator_fee, protocol_fees) of a curve entry, either [key, lam, owner, hex] or after-state."""
    if entry is None:
        return None
    d = bytes.fromhex(entry[-1])
    out = {'data_len': len(d), 'lamports': entry[-4] if len(entry) == 4 and isinstance(entry[-4], int) else entry[1]}
    if len(d) >= 141:
        out['creator_fee'], out['protocol_fees'] = struct.unpack_from('<QQ', d, CREATOR_FEE_OFF)
    return out


def token_amount(entry):
    if entry is None:
        return None
    d = bytes.fromhex(entry[-1])
    return struct.unpack_from('<Q', d, 64)[0] if len(d) >= 72 else None


def withheld(entry):
    """TransferFeeAmount.withheld_amount of a Token-2022 account (type byte, then TLV 2/8/amount)."""
    if entry is None:
        return None
    d = bytes.fromhex(entry[-1])
    return struct.unpack_from('<Q', d, 170)[0] if len(d) >= 178 else None


def summarize(cases, original, candidate):
    rows = []
    for c, ro, rc in zip(cases, original, candidate):
        before = {a[0]: a for a in c['accounts']}
        curve_before = before.get(str(CURVE))
        recipient = c['instructions'][-1]['metas'][9][0]
        row = {'case': c['case'], 'note': c['note'],
               'outcome': {'original': outcome(ro), 'candidate': outcome(rc)},
               'curve': {'before': fee_fields(curve_before),
                         'original_after': fee_fields(ro['accounts_after'].get(str(CURVE))),
                         'candidate_after': fee_fields(rc['accounts_after'].get(str(CURVE)))},
               'recipient_lamports': {'before': before[recipient][1] if recipient in before else 0,
                                      'original_after': (ro['accounts_after'].get(recipient) or [0])[0],
                                      'candidate_after': (rc['accounts_after'].get(recipient) or [0])[0]},
               'quote_accounts_after': {'source_tokens': token_amount(ro['accounts_after'].get(c['instructions'][-1]['metas'][8][0])),
                                        'destination_tokens': token_amount(ro['accounts_after'].get(c['instructions'][-1]['metas'][10][0])),
                                        'destination_withheld': withheld(ro['accounts_after'].get(c['instructions'][-1]['metas'][10][0]))},
               'payer_lamports_after': {'original': ro['payer_lamports_after'],
                                        'candidate': rc['payer_lamports_after']},
               'events': {'original': [decode_event(e) for e in ro['events']],
                          'candidate': [decode_event(e) for e in rc['events']]},
               'messages': {'original': ro['handler_messages'], 'candidate': rc['handler_messages']},
               'inner_instruction_count': {n: sum(len(x) for x in (r['inner_instructions'] or []))
                                           for n, r in (('original', ro), ('candidate', rc))},
               'compute_units': {'original': ro['compute_units'], 'candidate': rc['compute_units'],
                                 'original_minus_candidate': ro['compute_units'] - rc['compute_units'],
                                 'logged_original': logged_compute_units(ro['logs']),
                                 'logged_candidate': logged_compute_units(rc['logs'])},
               'logs_equal': ro['logs'] == rc['logs'],
               'differing_log_lines': classify_logs(ro['logs'], rc['logs']),
               'behavior_differences': [k for k in BEHAVIOR if ro[k] != rc[k]]}
        rows.append(row)
    outcomes, deltas, kinds = {}, {}, {}
    for r in rows:
        o = r['outcome']['original']
        outcomes[o] = outcomes.get(o, 0) + 1
        dk = str(r['compute_units']['logged_original'] - r['compute_units']['logged_candidate'])
        deltas[dk] = deltas.get(dk, 0) + 1
        kind = ','.join(sorted({d['kind'] for d in r['differing_log_lines']})) or 'none'
        kinds[kind] = kinds.get(kind, 0) + 1
    return {'case_count': len(rows),
            'behavior_mismatches': [r['case'] for r in rows if r['behavior_differences']],
            'outcome_mismatches': [r['case'] for r in rows if r['outcome']['original'] != r['outcome']['candidate']],
            'compute_units_equal_cases': sum(r['compute_units']['logged_original'] == r['compute_units']['logged_candidate'] for r in rows),
            'logs_equal_cases': sum(r['logs_equal'] for r in rows),
            'cases_by_outcome': dict(sorted(outcomes.items())),
            'compute_unit_delta_counts': dict(sorted(deltas.items(), key=lambda kv: int(kv[0]))),
            'log_difference_kinds': dict(sorted(kinds.items())),
            'cases': rows}



# ---- length probes: in-memory rewrite of one filename-length immediate ----

# (site line, error code, filename length in the original image, filename length in the rebuild)
SITES = {'l145': 145, 'l123': 123}
PIECES = ('AnchorError thrown in ', ':', '. Error Code: ', '. Error Number: ', '. Error Message: ', '.')
FORMAT_CAPACITY = 2 * sum(len(p) for p in PIECES)


def find_site(elf, line, filename_len):
    """Offset of `stdw [r10-560], <filename length>` that follows `stw [r10-552], <line>` in sweep::execute."""
    hits = []
    for q in range(0x120, len(elf) - 16, 8):
        op, regs, off, imm = struct.unpack_from('<BBhi', elf, q)
        if op == 0x7a and off == -560 and imm == filename_len:
            pop, _, poff, pimm = struct.unpack_from('<BBhi', elf, q - 8)
            if pop == 0x62 and poff == -552 and pimm == line:
                hits.append(q)
    assert len(hits) == 1, (line, hits)
    return hits[0]


def patched(elf, line, filename_len, new_len):
    site = find_site(elf, line, filename_len)
    out = bytearray(elf)
    struct.pack_into('<i', out, site + 4, new_len)
    return bytes(out)


def load_vm_bytes(elf):
    vm = LiteSVM().with_transaction_history(0).with_sigverify(False)
    programdata = Pubkey.find_program_address([bytes(PROGRAM)], UPGRADEABLE)[0]
    vm.set_account(programdata, Account(10**10, struct.pack('<IQB', 3, 0, 0) + bytes(32) + elf, UPGRADEABLE, False))
    vm.set_account(PROGRAM, Account(10**9, struct.pack('<I', 2) + bytes(programdata), UPGRADEABLE, True))
    vm.airdrop(PAYER, 10**11)
    return vm


def probe_plan():
    """Pure data: which site, which filename length; unpatched cases carry patch None."""
    wrong = dict(state=dict(recipient=str(FEE_RECIPIENT)), bucket='creator')
    probes = [{'case': 'unpatched-' + n, 'patch': None, 'base': n} for n in UNPATCHED]
    for n in list(range(0, 32)) + list(range(160, 164)):
        probes.append({'case': f'l145-filename-{n}', 'patch': {'line': 145, 'new_len': n}, 'base': 'creator-wrong-recipient'})
    for n in (0, 8, 16, 24, 31):
        probes.append({'case': f'l123-filename-{n}', 'patch': {'line': 123, 'new_len': n}, 'base': 'recipient-default'})
    return probes


UNPATCHED = ('fee-sum-overflow', 'reserves-sum-overflow', 'recipient-default', 'creator-wrong-recipient',
             'spl-source-missing', 'spl-source-foreign-owner', 'spl-dest-foreign-owner', 'protocol-unlisted')


def message(logs):
    m = [l[len('Program log: '):] for l in logs if l.startswith('Program log: AnchorError thrown in ')]
    return m[0] if len(m) == 1 else None


def run_probes(blobs):
    base = {c['case']: c for c in plan()}
    out = {'original': [], 'candidate': []}
    lens = {'original': 31, 'candidate': 17}
    for p in probe_plan():
        c = dict(base[p['base']], case=p['case'])
        for image in ('original', 'candidate'):
            elf = blobs[image]
            if p['patch']:
                elf = patched(elf, p['patch']['line'], lens[image], p['patch']['new_len'])
            vm = load_vm_bytes(elf)
            out[image].append(run_case(vm, 0, c))
    return out


def probe_rows(probes, res):
    rows = []
    for p, ro, rc in zip(probes, res['original'], res['candidate']):
        mo, mc = message(ro['logs']), message(rc['logs'])
        rows.append({'case': p['case'], 'patch': p['patch'], 'base_case': p['base'],
                     'error': outcome(ro), 'same_error': outcome(ro) == outcome(rc),
                     'message_len': {'original': len(mo.encode()), 'candidate': len(mc.encode())},
                     'logged_cu': {'original': logged_compute_units(ro['logs']),
                                   'candidate': logged_compute_units(rc['logs'])}})
    return rows


def step_table(rows):
    """CU minus message length, per image, for the probes of one site, in length order."""
    out = {}
    for image in ('original', 'candidate'):
        pts = sorted({(r['message_len'][image], r['logged_cu'][image]) for r in rows})
        out[image] = {'points': [[l, cu, cu - l] for l, cu in pts],
                      'distinct_cu_minus_len': sorted({cu - l for l, cu in pts})}
    return out


def predicted_gap(l_orig, l_cand, cap=None):
    cap = cap or FORMAT_CAPACITY
    return (l_orig - l_cand) + (104 if l_cand <= cap < l_orig else 0)


# ---- the same rule on the merged Pump Main packets' receipts ----

MERGED = ('pump-admin-cto-validation-boundaries-20261030', 'pump-claim-incentives-cashback-boundaries-20261030',
          'pump-create-v2-quote-mint-extension-allowlist-20261030', 'pump-creator-fee-collect-boundaries-20261030',
          'pump-global-admin-sequences-20261030', 'pump-instruction-decode-boundaries-20261030',
          'pump-quote-control-admin-lifecycle-20261030', 'pump-sell-historical-curve-layouts-20261030',
          'pump-token-incentive-schedule-boundaries-20261030', 'pump-trade-post-fee-quote-boundaries-20261030',
          'pump-v2-token-quote-curve-rent-topup-20261030', 'pump-v2-token-quote-transfer-fee-boundaries-20261030',
          'pump-v3-token-quote-boundaries-20261030', 'pump-v3-trade-boundaries-20261030')


def mine(root):
    table, sources = {}, {}
    for name in MERGED:
        for f in sorted((root / 'research' / name / 'runtime').glob('receipts*.jsonl.gz')):
            raw = f.read_bytes()
            sources[f'{name}/{f.name}'] = hashlib.sha256(raw).hexdigest()
            rows = {}
            for line in gzip.decompress(raw).decode().splitlines():
                r = json.loads(line)
                rows.setdefault((r.get('loader'), r.get('case')), {})[r.get('image')] = r.get('logs') or []
            for v in rows.values():
                if 'original' not in v or 'candidate' not in v:
                    continue
                so, sc = message(v['original']), message(v['candidate'])
                if so is None or sc is None or so == sc:
                    continue
                pump = lambda ls: [int(l.split(' consumed ')[1].split()[0]) for l in ls
                                   if l.startswith(f'Program {PROGRAM} consumed ')]
                co, cc = pump(v['original']), pump(v['candidate'])
                if not co or len(co) != len(cc):
                    continue
                key = f'{len(so)}/{len(sc)}/{so.split("Error Code: ")[1].split(".")[0]}'
                d = str(sum(co) - sum(cc))
                table.setdefault(key, {})
                table[key][d] = table[key].get(d, 0) + 1
    return {'sources': sources, 'sites': dict(sorted(table.items()))}


def mined_summary(mined):
    band, other = {}, {}
    n_band = n_other = 0
    for key, deltas in mined['sites'].items():
        lo, lc, _ = key.split('/', 2)
        in_band = int(lc) <= FORMAT_CAPACITY < int(lo)
        for d, count in deltas.items():
            target = band if in_band else other
            target[d] = target.get(d, 0) + count
            if in_band:
                n_band += count
            else:
                n_other += count
    ints = lambda t: [int(k) for k in t]
    return {'crossing_cases': n_band, 'crossing_delta_min': min(ints(band)), 'crossing_delta_max': max(ints(band)),
            'non_crossing_cases': n_other, 'non_crossing_delta_min': min(ints(other)),
            'non_crossing_delta_max': max(ints(other)),
            'crossing_delta_counts': dict(sorted(band.items(), key=lambda kv: int(kv[0]))),
            'non_crossing_delta_counts': dict(sorted(other.items(), key=lambda kv: int(kv[0])))}


def analyse(probes, res, mined):
    rows = probe_rows(probes, res)
    l145 = [r for r in rows if r['base_case'] == 'creator-wrong-recipient' and r['patch']]
    l123 = [r for r in rows if r['base_case'] == 'recipient-default' and r['patch']]
    unpatched = [r for r in rows if not r['patch']]
    for r in unpatched:
        r['gap'] = r['logged_cu']['original'] - r['logged_cu']['candidate']
        r['predicted_gap_from_message_lengths'] = predicted_gap(r['message_len']['original'], r['message_len']['candidate'])
    same = lambda rs: sum(r['logged_cu']['original'] == r['logged_cu']['candidate']
                          and r['message_len']['original'] == r['message_len']['candidate'] for r in rs)
    return {'format_pieces': list(PIECES), 'format_piece_bytes': FORMAT_CAPACITY // 2, 'format_capacity': FORMAT_CAPACITY,
            'probes': rows,
            'l145_equal_length_equal_cu': same(l145), 'l145_probes': len(l145),
            'l123_equal_length_equal_cu': same(l123), 'l123_probes': len(l123),
            'l145_steps': step_table(l145), 'l123_steps': step_table(l123),
            'merged_packets': mined_summary(mined)}


def write_gz(path, text):
    path.write_bytes(gzip.compress(text.encode(), mtime=0))


def receipts_text(probes, res):
    lines = []
    for p, ro, rc in zip(probes, res['original'], res['candidate']):
        lines += [json.dumps({'image': 'original', 'patch': p['patch'], **ro}, sort_keys=True, separators=(',', ':')),
                  json.dumps({'image': 'candidate', 'patch': p['patch'], **rc}, sort_keys=True, separators=(',', ':'))]
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--images', required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    images = json.loads(args.images)
    blobs = {n: Path(images[n]).read_bytes() for n in ('original', 'candidate')}
    for image, b in blobs.items():
        for piece in PIECES[:1] + PIECES[2:5]:
            assert piece.encode() in b, piece
    probes = probe_plan()
    assert len(probes) <= 60 and len({p['case'] for p in probes}) == len(probes), len(probes)
    runtime = args.out / 'runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    for old in runtime.glob('*'):
        old.unlink()
    base = {c['case']: c for c in plan()}
    write_gz(runtime / 'plan.json.gz', json.dumps({'probes': probes, 'base_cases': {p['base']: base[p['base']] for p in probes}},
                                                  sort_keys=True, indent=0) + '\n')
    res = run_probes(blobs)
    write_gz(runtime / 'receipts.jsonl.gz', receipts_text(probes, res))
    mined = mine(args.root)
    write_gz(runtime / 'merged-sites.json.gz', json.dumps(mined, sort_keys=True, indent=0) + '\n')
    report = {'scope': 'Pump Main AnchorError log line: cost of the message string against its format capacity, '
                       'measured with in-memory rewrites of one filename-length immediate in sweep::execute on both '
                       'images, unpatched control sites, and the receipts of merged Pump Main packets.',
              'images': {n: hashlib.sha256(b).hexdigest() for n, b in blobs.items()},
              'image_bytes': {n: len(b) for n, b in blobs.items()},
              'analysis': analyse(probes, res, mined)}
    write_gz(runtime / 'report.json.gz', json.dumps(report, sort_keys=True, indent=1) + '\n')
    a = report['analysis']
    print(json.dumps({k: a[k] for k in a if k not in ('probes', 'l145_steps', 'l123_steps')}, indent=1))
    print('l145', a['l145_steps']['original']['distinct_cu_minus_len'], a['l145_steps']['candidate']['distinct_cu_minus_len'])
    print('l123', a['l123_steps']['original']['distinct_cu_minus_len'], a['l123_steps']['candidate']['distinct_cu_minus_len'])
    for r in a['probes']:
        print(r['case'], r['error'][:30], r['message_len'], r['logged_cu'], r.get('gap'), r.get('predicted_gap_from_message_lengths'))


if __name__ == '__main__':
    main()
