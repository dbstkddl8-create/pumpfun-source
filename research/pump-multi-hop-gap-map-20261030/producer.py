#!/usr/bin/env python3
"""Pump Main multi_hop_curve_swap: map of the original-vs-rebuild CU gap by error site and route shape.

multi_hop_curve_swap::swap_hop (original window 0x5b3b0, 18,584 bytes) is an unmatched window with low
similarity. The cost of an AnchorError line is known from the message lengths (path bytes, plus 104 CU when
the rebuild's message fits the 142-byte format capacity and the original's does not, see
pump-anchor-error-format-capacity-cu-20261030). What is left of a failing case's gap is the instruction-count
difference accumulated up to that source line. Successes are compared by route shape.

The cases are those of pump-multi-hop-curve-swap-boundaries-20261030: the instruction is sent directly with
signature verification off, so the pump_amm_global_config PDA can sit in a signer slot. FeeConfig is read as
account data, so only the Pump image is loaded (upgradeable loader layout); SPL Token, Token-2022 and ATA
are LiteSVM built-ins. All state is synthetic, keys come from fixed seeds, the clock is fixed, one fresh VM per
case, no network. The full initial account set of every case is written to runtime/plan.json.gz.

Usage:
  python3 producer.py --root <repo> --images '{"original": "...", "candidate": "..."}' --out <packet dir>
"""
import argparse
import base64
import gzip
import hashlib
import json
import re
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
FEE_PROGRAM = Pubkey.from_string('pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ')
AMM_PROGRAM = Pubkey.from_string('pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA')
TOKEN = Pubkey.from_string('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA')
TOKEN22 = Pubkey.from_string('TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb')
ATA_PROGRAM = Pubkey.from_string('ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL')
WSOL = Pubkey.from_string('So11111111111111111111111111111111111111112')
SYSTEM = Pubkey.default()
USER = Keypair.from_seed(bytes([231]) * 32)
CREATOR = Pubkey(bytes([60]) * 32)
MINT = Keypair.from_seed(bytes([61]) * 32).pubkey()      # curve A: native SOL quote
OTHER_MINT = Keypair.from_seed(bytes([62]) * 32).pubkey()
MINT_B = Keypair.from_seed(bytes([65]) * 32).pubkey()    # curve B: quote = MINT (nested)
QUOTE_SPL = Keypair.from_seed(bytes([64]) * 32).pubkey()  # curve C: SPL quote
MINT_C = Keypair.from_seed(bytes([66]) * 32).pubkey()
FEE_RECIPIENT = Pubkey(bytes([90]) * 32)
FEE_RECIPIENTS = [Pubkey(bytes([110 + i]) * 32) for i in range(7)]
RESERVED = Pubkey(bytes([120]) * 32)
RESERVED_LIST = [Pubkey(bytes([121 + i]) * 32) for i in range(7)]
BUYBACK = [Pubkey(bytes([100 + i]) * 32) for i in range(8)]
STRANGER = Pubkey(bytes([200]) * 32)
BASE_TS = 1_800_000_000
CU_LIMIT = 1_400_000

DISC = {'Global': bytes([167, 232, 232, 177, 200, 108, 114, 127]),
        'BondingCurve': bytes([23, 183, 248, 55, 96, 216, 172, 96]),
        'FeeConfig': bytes([143, 52, 146, 187, 219, 123, 76, 155])}
IX = {'multi_hop_curve_swap': bytes([225, 154, 117, 22, 215, 86, 246, 103])}

pda = lambda seeds, program=PROGRAM: Pubkey.find_program_address(seeds, program)[0]
GLOBAL = pda([b'global'])
EVENT_AUTHORITY = pda([b'__event_authority'])
FEE_CONFIG = pda([b'fee_config', bytes(PROGRAM)], FEE_PROGRAM)
AMM_GLOBAL_CONFIG = pda([b'global_config'], AMM_PROGRAM)
CURVE = pda([b'bonding-curve', bytes(MINT)])
CURVE_B = pda([b'bonding-curve', bytes(MINT_B)])
CURVE_C = pda([b'bonding-curve', bytes(MINT_C)])


def qata(owner, mint, program=TOKEN):
    return pda([bytes(owner), bytes(program), bytes(mint)], ATA_PROGRAM)


V = {'vtr': 1_073_000_000_000_000, 'vqr': 30_000_000_000, 'rtr': 793_100_000_000_000,
     'rqr': 0, 'supply': 1_000_000_000_000_000}
RENT_166 = 2_046_240
NATIVE_RESERVE = 2_039_280


def global_data(**kw):
    d = bytearray(1088)
    d[:8] = DISC['Global']
    d[8] = 1
    d[9:41] = bytes(Pubkey(bytes([91]) * 32))
    d[41:73] = bytes(FEE_RECIPIENT)
    struct.pack_into('<QQQQQ', d, 73, V['vtr'], V['vqr'], V['rtr'], V['supply'], 95)
    struct.pack_into('<Q', d, 146, kw.get('migration_fee', 0))
    struct.pack_into('<Q', d, 154, 30)
    for i, k in enumerate(FEE_RECIPIENTS):
        d[162 + 32 * i:194 + 32 * i] = bytes(k)
    d[450] = 1
    d[451:483] = bytes(kw.get('whitelist', Pubkey(bytes([92]) * 32)))
    d[483:515] = bytes(RESERVED)
    d[515] = 1
    for i, k in enumerate(RESERVED_LIST):
        d[516 + 32 * i:548 + 32 * i] = bytes(k)
    for i, k in enumerate(BUYBACK):
        d[741 + 32 * i:773 + 32 * i] = bytes(k)
    struct.pack_into('<QQ', d, 997, kw.get('buyback_bps', 5000), V['vqr'])
    return bytes(d)


def curve_data(**kw):
    c = dict(V, complete=0, creator=CREATOR, mayhem=0, cashback=0, quote_mint=SYSTEM)
    c.update(kw)
    d = bytearray(166)
    d[:8] = DISC['BondingCurve']
    struct.pack_into('<QQQQQ', d, 8, c['vtr'], c['vqr'], c['rtr'], c['rqr'], c['supply'])
    d[48] = c['complete']
    d[49:81] = bytes(c['creator'])
    d[81] = c['mayhem']
    d[82] = c['cashback']
    d[83:115] = bytes(c['quote_mint'])
    struct.pack_into('<QQ', d, 125, c.get('creator_fee', 0), c.get('protocol_fees', 0))
    return bytes(d)


def mint_data(supply=V['supply'], decimals=6):
    return struct.pack('<I32sQBBI32s', 0, bytes(32), supply, decimals, 1, 0, bytes(32))


def token_data(mint, owner, amount, native=None):
    tag, val = (0, 0) if native is None else (1, native)
    return struct.pack('<32s32sQI32sBIQQI32s', bytes(mint), bytes(owner), amount, 0, bytes(32), 1, tag, val,
                       0, 0, bytes(32))


def fee_config(length=2512, tiers=((0, 95, 30),), flat=(0, 90, 20), disc=None):
    """FeeConfig: disc | bump | admin | flat_fees | fee_tiers vec<(u128 threshold, Fees)> | stable vec | exotic."""
    bump = Pubkey.find_program_address([b'fee_config', bytes(PROGRAM)], FEE_PROGRAM)[1]
    d = (disc or DISC['FeeConfig']) + bytes([bump]) + bytes(Pubkey(bytes([93]) * 32)) + struct.pack('<QQQ', *flat)
    d += struct.pack('<I', len(tiers))
    for threshold, pb, cb in tiers:
        d += threshold.to_bytes(16, 'little') + struct.pack('<QQQ', 0, pb, cb)
    d += struct.pack('<I', 0) + struct.pack('<QQQ', 0, 0, 0)
    return d.ljust(length, b'\0')[:length]


SELL_KW = {'rqr': 10**11, 'rtr': V['rtr'] - 10**14, 'vtr': V['vtr'] - 10**14, 'vqr': V['vqr'] + 10**11}


def state(a=None, b=None, c=None, glob_kw=None, fee_kw=None, fee_owner=FEE_PROGRAM, user_a=10**14, user_b=10**14,
          user_spl=10**15, user_c=10**14, extra=None):
    """Curve A (native SOL quote), optional curve B (quote = A tokens) and curve C (SPL quote)."""
    a = dict(a or {})
    st = {
        GLOBAL: (10**9, PROGRAM, global_data(**(glob_kw or {}))),
        FEE_CONFIG: (10**9, fee_owner, fee_config(**(fee_kw or {}))),
        USER.pubkey(): (10**13, SYSTEM, b''),
        MINT: (10**9, TOKEN, mint_data()),
        OTHER_MINT: (10**9, TOKEN, mint_data()),
        WSOL: (10**9, TOKEN, mint_data(0, 9)),
        CURVE: (RENT_166 + a.get('rqr', 0), PROGRAM, curve_data(**a)),
        qata(CURVE, MINT): (10**9, TOKEN, token_data(MINT, CURVE, a.pop('curve_tokens', a.get('rtr', V['rtr'])))),
        qata(USER.pubkey(), MINT): (10**9, TOKEN, token_data(MINT, USER.pubkey(), user_a)),
        qata(USER.pubkey(), WSOL): (NATIVE_RESERVE, TOKEN, token_data(WSOL, USER.pubkey(), 0, NATIVE_RESERVE)),
        qata(USER.pubkey(), OTHER_MINT): (10**9, TOKEN, token_data(OTHER_MINT, USER.pubkey(), 10**14)),
        qata(BUYBACK[0], WSOL): (NATIVE_RESERVE, TOKEN, token_data(WSOL, BUYBACK[0], 0, NATIVE_RESERVE)),
        STRANGER: (10**9, SYSTEM, b''),
    }
    st[CURVE] = (RENT_166 + a.get('rqr', 0), PROGRAM, curve_data(**a))
    if b is not None:
        b = dict(b)
        b.setdefault('quote_mint', MINT)
        st[MINT_B] = (10**9, TOKEN, mint_data())
        st[qata(CURVE_B, MINT_B)] = (10**9, TOKEN, token_data(MINT_B, CURVE_B, b.pop('curve_tokens', b.get('rtr', V['rtr']))))
        st[qata(CURVE_B, MINT)] = (10**9, TOKEN, token_data(MINT, CURVE_B, b.get('rqr', 0)))
        st[CURVE_B] = (RENT_166, PROGRAM, curve_data(**b))
        st[qata(USER.pubkey(), MINT_B)] = (10**9, TOKEN, token_data(MINT_B, USER.pubkey(), user_b))
        st[qata(BUYBACK[0], MINT)] = (10**9, TOKEN, token_data(MINT, BUYBACK[0], 0))
    if c is not None:
        c = dict(c)
        c.setdefault('quote_mint', QUOTE_SPL)
        st[MINT_C] = (10**9, TOKEN, mint_data())
        st[QUOTE_SPL] = (10**9, TOKEN, mint_data(10**16, 6))
        st[CURVE_C] = (RENT_166, PROGRAM, curve_data(**c))
        st[qata(CURVE_C, MINT_C)] = (10**9, TOKEN, token_data(MINT_C, CURVE_C, c.get('rtr', V['rtr'])))
        st[qata(CURVE_C, QUOTE_SPL)] = (10**9, TOKEN, token_data(QUOTE_SPL, CURVE_C, c.get('rqr', 0)))
        st[qata(USER.pubkey(), MINT_C)] = (10**9, TOKEN, token_data(MINT_C, USER.pubkey(), user_c))
        st[qata(USER.pubkey(), QUOTE_SPL)] = (10**9, TOKEN, token_data(QUOTE_SPL, USER.pubkey(), user_spl))
        st[qata(BUYBACK[0], QUOTE_SPL)] = (10**9, TOKEN, token_data(QUOTE_SPL, BUYBACK[0], 0))
    st.update(extra or {})
    return st


HOPS = {'A': (MINT, WSOL, CURVE), 'B': (MINT_B, MINT, CURVE_B), 'C': (MINT_C, QUOTE_SPL, CURVE_C)}


def hop(name, **over):
    base, quote, curve = HOPS[name]
    o = {'base_mint': base, 'quote_mint': quote, 'curve': curve, 'base_ata': qata(curve, base),
         'quote_ata': qata(curve, quote)}
    o.update(over)
    w = lambda k: AccountMeta(k, False, True)
    r = lambda k: AccountMeta(k, False, False)
    return [r(o['base_mint']), r(o['quote_mint']), w(o['curve']), w(o['base_ata']), w(o['quote_ata'])]


def metas(source, destination, hops, over=None):
    o = {'global': GLOBAL, 'fee_config': FEE_CONFIG, 'amm': AMM_GLOBAL_CONFIG, 'amm_signer': True,
         'buyback': qata(BUYBACK[0], WSOL), 'source_authority': USER.pubkey(), 'token_program': TOKEN}
    o.update(over or {})
    out = [AccountMeta(o['global'], False, False), AccountMeta(o['fee_config'], False, False),
           AccountMeta(o['amm'], o['amm_signer'], False), AccountMeta(USER.pubkey(), True, True),
           AccountMeta(o['source_authority'], True, False), AccountMeta(source, False, True),
           AccountMeta(destination, False, True), AccountMeta(o['buyback'], False, True),
           AccountMeta(o['token_program'], False, False), AccountMeta(TOKEN22, False, False),
           AccountMeta(SYSTEM, False, False), AccountMeta(EVENT_AUTHORITY, False, False),
           AccountMeta(PROGRAM, False, False)]
    for h in hops:
        out += h
    return out


def ix_data(amount, flags):
    return IX['multi_hop_curve_swap'] + struct.pack('<QI', amount, len(flags)) + bytes(flags)


def case(name, amount, flags, st, ms, note=''):
    return {'case': name, 'instruction': 'multi_hop_curve_swap', 'note': note, 'data_hex': ix_data(amount, flags).hex(),
            'metas': [[str(m.pubkey), m.is_signer, m.is_writable] for m in ms],
            'accounts': [[str(k), lam, str(owner), data.hex()] for k, (lam, owner, data) in
                         sorted(st.items(), key=lambda kv: str(kv[0]))]}


U_WSOL, U_A = qata(USER.pubkey(), WSOL), qata(USER.pubkey(), MINT)
U_B, U_C, U_SPL = qata(USER.pubkey(), MINT_B), qata(USER.pubkey(), MINT_C), qata(USER.pubkey(), QUOTE_SPL)
SOL = 10**9


def plan():
    out = []
    add = lambda *a, **k: out.append(case(*a, **k))
    S = state
    buy_a = lambda **o: metas(U_WSOL, U_A, [hop('A')], o)
    sell_a = lambda **o: metas(U_A, U_WSOL, [hop('A')], o)
    T = 10**12
    # ---- pre-loop argument checks ----
    add('pre/amount-zero', 0, [3], S(), buy_a(), note='amount_in 0 -> BuyZeroAmount before remaining-account checks')
    add('pre/remaining-0', SOL, [3], S(), metas(U_WSOL, U_A, []), note='no hop accounts')
    add('pre/remaining-4', SOL, [3], S(), metas(U_WSOL, U_A, [hop('A')[:4]]), note='4 remaining accounts')
    add('pre/remaining-6', SOL, [3], S(), metas(U_WSOL, U_A, [hop('A') + hop('A')[:1]]), note='6 remaining accounts')
    add('pre/hop-fees-empty', SOL, [], S(), buy_a(), note='hop_fees length 0 for 1 hop')
    add('pre/hop-fees-2-for-1', SOL, [3, 3], S(), buy_a(), note='hop_fees length 2 for 1 hop')
    add('pre/hop-fee-4', SOL, [4], S(), buy_a(), note='flag value 4 (limit is < 4)')
    # ---- outer context constraints ----
    add('ctx/amm-config-not-signer', SOL, [3], S(), buy_a(amm_signer=False), note='pump_amm global_config PDA not a signer')
    add('ctx/amm-config-wrong-key', SOL, [3], S(), buy_a(amm=STRANGER), note='other signer in the global_config slot')
    add('ctx/fee-config-owner-pump', SOL, [3], S(fee_owner=PROGRAM), buy_a(), note='FeeConfig owned by pump, not pump_fees')
    add('ctx/fee-config-bad-disc', SOL, [3], S(fee_kw={'disc': bytes(8)}), buy_a(), note='FeeConfig discriminator zeroed')
    add('ctx/fee-config-len-2511', SOL, [3], S(fee_kw={'length': 2511}), buy_a(), note='FeeConfig 1 byte under 2512')
    add('ctx/fee-config-len-2511-flags-0', SOL, [0], S(fee_kw={'length': 2511}), buy_a(), note='short FeeConfig, no fee flags')
    add('ctx/fee-config-tiers-empty', SOL, [0], S(fee_kw={'tiers': ()}), buy_a(), note='SOL tiers empty, flags 0')
    # ---- per-hop admission ----
    add('hop/quote-mint-other', SOL, [3], S(), metas(U_OTHER := qata(USER.pubkey(), OTHER_MINT), U_A,
                                                       [hop('A', quote_mint=OTHER_MINT)]),
        note='native curve with a non-WSOL quote mint -> MintDoesNotMatchBondingCurve')
    add('hop/complete', SOL, [3], S(a={'complete': 1}), buy_a(), note='curve.complete = 1')
    add('hop/mayhem', SOL, [3], S(a={'mayhem': 1}), buy_a(), note='mayhem curve')
    add('hop/cashback-flag-1', SOL, [1], S(a={'cashback': 1}), buy_a(), note='cashback coin, creator bit clear')
    add('hop/cashback-flag-2', SOL, [2], S(a={'cashback': 1}), buy_a(), note='cashback coin, creator bit set')
    add('hop/base-ata-wrong', SOL, [3], S(extra={STRANGER: (10**9, TOKEN, token_data(MINT, CURVE, V['rtr']))}),
        metas(U_WSOL, U_A, [hop('A', base_ata=STRANGER)]), note='curve base token account at a non-ATA address')
    add('hop/quote-ata-wrong', SOL, [3], S(), metas(U_WSOL, U_A, [hop('A', quote_ata=STRANGER)]),
        note='native curve quote ATA slot holds another key')
    add('hop/source-mint-unrelated', SOL, [3], S(), metas(U_OTHER, U_A, [hop('A')]),
        note='source mint is neither base nor quote -> MultiHopDiscontinuousPath')
    add('hop/destination-mint-wrong', SOL, [3], S(), metas(U_WSOL, U_OTHER, [hop('A')]),
        note='buy: destination mint != base mint; the last-hop base transfer reaches SPL Token first')
    add('hop/destination-mint-wrong-sell', T, [3], S(a=SELL_KW), metas(U_A, U_OTHER, [hop('A')]),
        note='native sell: destination untouched, final mint check after the hop')
    add('hop/buyback-wallet-flag-1', SOL, [1], S(), buy_a(buyback=BUYBACK[0]), note='buyback slot = listed wallet, protocol bit set')
    add('hop/buyback-wallet-flag-2', SOL, [2], S(), buy_a(buyback=STRANGER), note='unlisted wallet, protocol bit clear (not validated)')
    add('hop/buyback-unlisted-ata', SOL, [1], S(extra={qata(STRANGER, WSOL): (NATIVE_RESERVE, TOKEN, token_data(WSOL, STRANGER, 0, NATIVE_RESERVE))}),
        buy_a(buyback=qata(STRANGER, WSOL)), note='WSOL ATA of an owner not in the Global buyback list')
    add('hop/buyback-listed-7', SOL, [1], S(extra={qata(BUYBACK[7], WSOL): (NATIVE_RESERVE, TOKEN, token_data(WSOL, BUYBACK[7], 0, NATIVE_RESERVE))}),
        buy_a(buyback=qata(BUYBACK[7], WSOL)), note='last buyback list slot')
    # ---- native SOL buys / sells ----
    for f in range(4):
        add(f'buy/native-flag-{f}', SOL, [f], S(), buy_a(), note=f'1 SOL in, flag {f}')
    add('buy/native-1-lamport', 1, [3], S(), buy_a(), note='1 lamport in')
    add('buy/native-100-lamports-flag-0', 100, [0], S(), buy_a(), note='100 lamports, no fees')
    add('buy/native-buyback-bps-0', SOL, [1], S(glob_kw={'buyback_bps': 0}), buy_a(), note='Global buyback_basis_points 0')
    full = {'curve_tokens': V['supply']}
    add('buy/native-cross', 200 * SOL, [3], S(a=full), buy_a(), note='budget above the remaining curve: post-complete fill')
    add('buy/native-cross-flag-0', 200 * SOL, [0], S(a=full), buy_a(), note='crossing without fees')
    add('buy/native-cross-whitelist', 200 * SOL, [3], S(a=full, glob_kw={'whitelist': USER.pubkey()}), buy_a(),
        note='crossing by Global.whitelist_pda -> NotEnoughTokensToBuy')
    add('buy/native-cross-pool-base-0', 200 * SOL, [3], S(), buy_a(), note='crossing with curve base ATA = real_token_reserves')
    for f in range(4):
        add(f'sell/native-flag-{f}', T, [f], S(a=SELL_KW), sell_a(), note=f'sell 1e12 base, flag {f}')
    add('sell/native-1-unit', 1, [3], S(a=SELL_KW), sell_a(), note='sell 1 base unit -> quote 0')
    add('sell/native-user-short', 10**15, [3], S(a=SELL_KW), sell_a(), note='sell above user base balance')
    add('sell/native-above-rqr', 2 * 10**14, [0], S(a={**SELL_KW, 'rqr': 10**9}, user_a=10**15), sell_a(),
        note='gross quote above real_quote_reserves (1e9)')
    # ---- SPL quote curve ----
    spl_bb = qata(BUYBACK[0], QUOTE_SPL)
    add('spl/buy-flag-3', SOL, [3], S(c={}), metas(U_SPL, U_C, [hop('C')], {'buyback': spl_bb}), note='SPL quote buy, flat fees 90/20')
    add('spl/buy-flag-1-wsol-buyback', SOL, [1], S(c={}), metas(U_SPL, U_C, [hop('C')]), note='SPL quote, buyback = WSOL ATA')
    add('spl/sell-flag-3', T, [3], S(c=SELL_KW), metas(U_C, U_SPL, [hop('C')], {'buyback': spl_bb}), note='SPL quote sell')
    add('spl/sell-curve-quote-short', T, [3], S(c={**SELL_KW, 'rqr': 10**11}, extra={qata(CURVE_C, QUOTE_SPL): (10**9, TOKEN, token_data(QUOTE_SPL, CURVE_C, 10))}),
        metas(U_C, U_SPL, [hop('C')], {'buyback': spl_bb}), note='curve quote ATA balance below the payout')
    # ---- two-hop routes ----
    nested_bb = qata(BUYBACK[0], MINT)
    DEEP_B = {'vqr': 10**16}  # quote = A tokens: deep enough that 1 SOL of A does not cross curve B
    SELL_B = {'rqr': 10**14, 'rtr': V['rtr'] - 10**14, 'vtr': V['vtr'] - 10**14, 'vqr': 10**16 + 10**14}
    add('route/sol-a-b-flags-00', SOL, [0, 0], S(b=DEEP_B), metas(U_WSOL, U_B, [hop('A'), hop('B')]), note='SOL -> A -> B, no fees')
    add('route/sol-a-b-flags-23', SOL, [2, 3], S(b=DEEP_B), metas(U_WSOL, U_B, [hop('A'), hop('B')], {'buyback': nested_bb}),
        note='SOL -> A -> B, creator fee on hop 1, both fees on hop 2 (buyback in A)')
    add('route/sol-a-b-flags-31', SOL, [3, 1], S(b=DEEP_B), metas(U_WSOL, U_B, [hop('A'), hop('B')]),
        note='protocol fee on both hops; recipient is WSOL, hop 2 quote is A')
    add('route/b-a-sol-flags-00', T, [0, 0], S(a=SELL_KW, b={**DEEP_B, **SELL_B}), metas(U_B, U_WSOL, [hop('B'), hop('A')]),
        note='B -> A -> SOL, no fees')
    add('route/b-a-sol-flags-02', T, [0, 2], S(a=SELL_KW, b={**DEEP_B, **SELL_B}), metas(U_B, U_WSOL, [hop('B'), hop('A')]),
        note='B -> A -> SOL, creator fee on hop 2')
    add('route/a-roundtrip', SOL, [0, 0], S(), metas(U_WSOL, U_WSOL, [hop('A'), hop('A')]),
        note='buy A then sell A on the same curve (vault == destination, transfer skipped)')
    add('route/discontinuous', SOL, [0, 0], S(c={}), metas(U_WSOL, U_C, [hop('A'), hop('C')]),
        note='A output does not feed curve C -> MultiHopDiscontinuousPath')
    add('route/sol-a-b-cross-b', 30 * SOL, [0, 0], S(a=full, b={**DEEP_B, 'rtr': 10**9, 'curve_tokens': V['supply']}), metas(U_WSOL, U_B, [hop('A'), hop('B')]),
        note='hop 2 curve has 1e9 tokens left: post-complete branch on the nested curve')
    # ---- accrual ----
    U64 = 2**64 - 1
    add('acc/creator-fee-max', SOL, [3], S(a={'creator_fee': U64}), buy_a(), note='curve.creator_fee at u64::MAX, creator bit set')
    add('acc/creator-fee-max-flag-1', SOL, [1], S(a={'creator_fee': U64}), buy_a(), note='same, creator bit clear')
    return out


POST_COMPLETE_EVENT = bytes.fromhex('6fb06d8b316cd5fb')
POST_FIELDS = ('timestamp', 'base_out', 'quote_in', 'fee_basis_points', 'fee', 'creator_fee_basis_points', 'creator_fee',
               'buyback_fee', 'pool_base_reserves_before', 'pool_quote_reserves_before', 'pool_base_reserves_after',
               'pool_quote_reserves_after')


def post_complete_events(receipt):
    out = []
    for e in receipt['events']:
        d = base64.b64decode(e)
        if d[:8] == POST_COMPLETE_EVENT and len(d) >= 8 + 128 + 96:
            out.append(dict(zip(POST_FIELDS, struct.unpack_from('<q11Q', d, 8 + 128))))
    return out


def trade_event_tail(d):
    """TradeEvent fields after creator_fee (IDL order): buyback fee, quote mint, quote amount and reserves."""
    o = 8 + 32 + 17 + 32 + 8 + 32 + 32 + 16 + 32 + 16  # through creator_fee
    o += 1 + 24 + 8  # track_volume, total_unclaimed/claimed, current_sol_volume, last_update_timestamp
    o += 4 + struct.unpack_from('<I', d, o)[0] + 1 + 16  # ix_name, mayhem_mode, cashback bps, cashback
    buyback_bps, buyback_fee = struct.unpack_from('<QQ', d, o)
    o += 16
    o += 4 + struct.unpack_from('<I', d, o)[0] * 34  # shareholders (pubkey + u16)
    quote_amount, vqr, rqr = struct.unpack_from('<QQQ', d, o + 32)
    return {'buyback_fee_basis_points': buyback_bps, 'buyback_fee': buyback_fee, 'quote_mint': str(Pubkey(d[o:o + 32])),
            'quote_amount': quote_amount, 'virtual_quote_reserves': vqr, 'real_quote_reserves': rqr}


# ---- execution (verify.py carries an identical copy of everything below) ----

LOADERS = ('upgradeable',)
UPGRADEABLE = Pubkey.from_string('BPFLoaderUpgradeab1e11111111111111111111111')




def load_vm(image):
    """Pump under the upgradeable loader (program account + programdata, the mainnet layout).
    multi_hop_curve_swap reads FeeConfig as plain account data; no pump_fees program is loaded."""
    # Signature verification off: the pump_amm global_config PDA occupies a signer slot (on mainnet
    # pump_amm signs for it via CPI). The user/payer signature is still produced.
    vm = LiteSVM().with_transaction_history(0).with_sigverify(False)
    elf = Path(image).read_bytes()
    programdata = Pubkey.find_program_address([bytes(PROGRAM)], UPGRADEABLE)[0]
    vm.set_account(programdata, Account(10**10, struct.pack('<IQB', 3, 0, 0) + bytes(32) + elf,
                                        UPGRADEABLE, False))
    vm.set_account(PROGRAM, Account(10**9, struct.pack('<I', 2) + bytes(programdata), UPGRADEABLE, True))
    return vm


def run_case(vm, index, c):
    vm.expire_blockhash()
    vm.set_clock(Clock(1000 + index, 0, 0, 0, BASE_TS + index))
    keys = []
    for k, lam, owner, data in c['accounts']:
        key = Pubkey.from_string(k)
        keys.append(key)
        vm.set_account(key, Account(lam, bytes.fromhex(data), Pubkey.from_string(owner)))
    metas = [AccountMeta(Pubkey.from_string(k), s, w) for k, s, w in c['metas']]
    ixs = [Instruction(PROGRAM, bytes.fromhex(c['data_hex']), metas)]
    for t in c.get('then', []):  # multi-instruction sequence: later trades in the same transaction
        ixs.append(Instruction(PROGRAM, bytes.fromhex(t['data_hex']),
                               [AccountMeta(Pubkey.from_string(k), s, w) for k, s, w in t['metas']]))
    ixs.insert(0, set_compute_unit_limit(CU_LIMIT))  # multi-hop routes exceed the 200k default
    payer = Keypair.from_seed(bytes([231]) * 32)
    tx = Transaction.new_unsigned(Message.new_with_blockhash(ixs, payer.pubkey(), vm.latest_blockhash()))
    tx.partial_sign([payer], vm.latest_blockhash())  # the PDA signature slot stays zero
    result = vm.send_transaction(tx)
    failed = isinstance(result, FailedTransactionMetadata)
    meta = result.meta() if failed else result
    logs = list(meta.logs())
    ret = meta.return_data()
    after = {}
    for key in sorted(set(keys) | {m.pubkey for m in metas}, key=str):
        if key == PROGRAM:
            continue
        a = vm.get_account(key)
        if a is not None and not a.executable and (a.lamports or a.data):
            after[str(key)] = [a.lamports, str(a.owner), bytes(a.data).hex()]
    return {'case': c['case'], 'instruction': c['instruction'],
            'transaction_base64': base64.b64encode(bytes(tx)).decode(),
            'error': str(result.err()) if failed else None,
            'return_data_hex': bytes(ret.data).hex() if ret is not None else '',
            'events': [l[14:] for l in logs if l.startswith('Program data: ')],
            'inner_instructions': json.loads(meta.to_json())['inner_instructions'],
            'accounts_after': after, 'compute_units': meta.compute_units_consumed(), 'logs': logs}


def run_plan(image, loader, cases):
    assert loader in LOADERS
    return [run_case(load_vm(image), i, c) for i, c in enumerate(cases)]  # one fresh VM per case


BEHAVIOR = ('transaction_base64', 'error', 'return_data_hex', 'events',
            'inner_instructions', 'accounts_after')
SITE = 'Program log: AnchorError thrown in '


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
        elif ' consumed ' in a and ' consumed ' in b:
            out.append({'kind': 'consumed', 'original': a, 'candidate': b})
        else:
            out.append({'kind': 'other', 'original': a, 'candidate': b})
    return out


def custom_code(error):
    if error and 'Custom(' in error:
        return int(error.split('Custom(', 1)[1].split(')', 1)[0])
    return error


def anchor_name(logs):
    for line in logs:
        if 'Error Code: ' in line:
            return line.split('Error Code: ', 1)[1].split('.', 1)[0]
    return None


# ---- report ----

TRADE_EVENT = bytes.fromhex('bddb7fd34ee661ee')


def trade_events(receipt):
    return [t for t in (trade_event(e) for e in receipt['events']) if t is not None]


def trade_event(e):
    if True:
        d = base64.b64decode(e)
        if d[:8] != TRADE_EVENT or len(d) < 266:
            return None
        o = 8 + 32
        sol, tokens, is_buy = struct.unpack_from('<QQB', d, o)
        vsr, vtr, rsr, rtr = struct.unpack_from('<QQQQ', d, o + 17 + 32 + 8)
        o += 17 + 32 + 8 + 32 + 32
        fee_bps, fee = struct.unpack_from('<QQ', d, o)
        creator_fee_bps, creator_fee = struct.unpack_from('<QQ', d, o + 16 + 32)
        return {**trade_event_tail(d), 'sol_amount': sol, 'token_amount': tokens, 'is_buy': bool(is_buy), 'fee_basis_points': fee_bps,
                'fee': fee, 'creator_fee_basis_points': creator_fee_bps, 'creator_fee': creator_fee,
                'virtual_sol_reserves': vsr, 'virtual_token_reserves': vtr, 'real_sol_reserves': rsr,
                'real_token_reserves': rtr}
    return None


def curve_after(receipt):
    out = {}
    for name, curve in (('A', CURVE), ('B', CURVE_B), ('C', CURVE_C)):
        a = receipt['accounts_after'].get(str(curve))
        if a is None:
            continue
        d = bytes.fromhex(a[2])
        vtr, vqr, rtr, rqr, tts = struct.unpack_from('<QQQQQ', d, 8)
        cf, pf = struct.unpack_from('<QQ', d, 125)
        pbo, pqi = struct.unpack_from('<QQ', d, 150)
        out[name] = {'lamports': a[0], 'virtual_token_reserves': vtr, 'virtual_quote_reserves': vqr,
                     'real_token_reserves': rtr, 'real_quote_reserves': rqr, 'complete': d[48],
                     'creator_fee': cf, 'protocol_fees': pf, 'post_complete_base_out': pbo,
                     'post_complete_quote_in': pqi}
    return out


def token_deltas(c, receipt):
    """Token amount changes of every SPL token account in the case (label -> delta)."""
    before = {k: (owner, data) for k, _, owner, data in c['accounts']}
    out = {}
    for k, v in receipt['accounts_after'].items():
        if v[1] != str(TOKEN) or len(v[2]) < 165 * 2:
            continue
        d = bytes.fromhex(v[2])
        if len(d) != 165:
            continue
        b = before.get(k)
        old = struct.unpack_from('<Q', bytes.fromhex(b[1]), 64)[0] if b and len(b[1]) == 330 else 0
        new = struct.unpack_from('<Q', d, 64)[0]
        if new != old:
            out[LABELS.get(k, k)] = new - old
    return dict(sorted(out.items()))


LABELS = {str(USER.pubkey()): 'user', str(CURVE): 'curve_A', str(CURVE_B): 'curve_B', str(CURVE_C): 'curve_C',
          str(qata(CURVE, MINT)): 'curve_A_base', str(qata(CURVE_B, MINT_B)): 'curve_B_base',
          str(qata(CURVE_B, MINT)): 'curve_B_quote', str(qata(CURVE_C, MINT_C)): 'curve_C_base',
          str(qata(CURVE_C, QUOTE_SPL)): 'curve_C_quote', str(U_WSOL): 'user_wsol', str(U_A): 'user_A',
          str(U_B): 'user_B', str(U_C): 'user_C', str(U_SPL): 'user_spl', str(qata(BUYBACK[0], WSOL)): 'buyback_wsol',
          str(qata(BUYBACK[0], MINT)): 'buyback_A', str(qata(BUYBACK[0], QUOTE_SPL)): 'buyback_spl',
          str(qata(BUYBACK[7], WSOL)): 'buyback7_wsol', str(qata(STRANGER, WSOL)): 'stranger_wsol', str(STRANGER): 'stranger',
          str(BUYBACK[0]): 'buyback_wallet'}


def lamport_deltas(c, receipt):
    before = {k: lam for k, lam, _, _ in c['accounts']}
    out = {}
    for k, v in receipt['accounts_after'].items():
        delta = v[0] - before.get(k, 0)
        if delta:
            out[LABELS.get(k, k)] = delta
    return dict(sorted(out.items()))


FORMAT_CAPACITY = 142
REALLOC_CU = 104
SITE_RE = re.compile(r'AnchorError thrown in (\S+?):(\d+)\. Error Code: (\w+)\.')


def anchor_line(logs):
    m = [l[len('Program log: '):] for l in logs if l.startswith('Program log: AnchorError thrown in ')]
    return m[0] if len(m) == 1 else None


def message_cost_gap(l_orig, l_cand):
    return l_orig - l_cand + (REALLOC_CU if l_cand <= FORMAT_CAPACITY < l_orig else 0)


def gap_map(cases, original, candidate):
    sites, successes = {}, []
    for c, ro, rc in zip(cases, original, candidate):
        gap = ro['compute_units'] - rc['compute_units']
        so, sc = anchor_line(ro['logs']), anchor_line(rc['logs'])
        if so is None:
            if ro['error'] is None:
                successes.append({'case': c['case'], 'gap': gap, 'note': c['note']})
            continue
        path, line, code = SITE_RE.search(so).groups()
        cost = message_cost_gap(len(so), len(sc))
        key = f'{int(line):05d}/{code}/{gap}'
        e = sites.setdefault(key, {'file': path.split('/')[-1], 'line': int(line), 'error': code,
                                   'message_len': [len(so), len(sc)], 'gap': gap, 'message_cost_gap': cost,
                                   'remainder': gap - cost, 'cases': []})
        e['cases'].append(c['case'])
    return {'failing_sites': [sites[k] for k in sorted(sites)], 'successes': sorted(successes, key=lambda x: x['gap'])}


def summarize(cases, original, candidate):
    rows = []
    for c, ro, rc in zip(cases, original, candidate):
        rows.append({'case': c['case'], 'instruction': c['instruction'], 'note': c['note'],
                     'error_original': ro['error'], 'error_candidate': rc['error'],
                     'custom_code': custom_code(ro['error']),
                     'error_name': {'original': anchor_name(ro['logs']), 'candidate': anchor_name(rc['logs'])},
                     'compute_units': {'original': ro['compute_units'], 'candidate': rc['compute_units'],
                                       'original_minus_candidate': ro['compute_units'] - rc['compute_units']},
                     'logs_equal': ro['logs'] == rc['logs'],
                     'differing_log_lines': classify_logs(ro['logs'], rc['logs']),
                     'behavior_differences': [k for k in BEHAVIOR if ro[k] != rc[k]],
                     'trade_events': trade_events(ro), 'post_complete_events': post_complete_events(ro),
                     'curve_after': curve_after(ro),
                     'lamport_deltas': lamport_deltas(c, ro), 'token_deltas': token_deltas(c, ro)})
    stops, deltas, kinds = {}, {}, {}
    for r in rows:
        stop = 'success' if r['error_original'] is None else (r['error_name']['original'] or str(r['custom_code']))
        stops[stop] = stops.get(stop, 0) + 1
        dk = f"{r['compute_units']['original_minus_candidate']}:{stop}"
        deltas[dk] = deltas.get(dk, 0) + 1
        kind = ','.join(sorted({d['kind'] for d in r['differing_log_lines']})) or 'none'
        kinds[kind] = kinds.get(kind, 0) + 1
    return {'case_count': len(rows), 'gap_map': gap_map(cases, original, candidate),
            'behavior_mismatches': [r['case'] for r in rows if r['behavior_differences']],
            'compute_units_equal_cases': sum(r['compute_units']['original_minus_candidate'] == 0 for r in rows),
            'logs_equal_cases': sum(r['logs_equal'] for r in rows),
            'cases_by_stop': dict(sorted(stops.items())),
            'compute_unit_delta_by_stop': dict(sorted(deltas.items())),
            'log_difference_kinds': dict(sorted(kinds.items())),
            'cases': rows}


def write_gz(path, text):
    path.write_bytes(gzip.compress(text.encode(), mtime=0))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--images', required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    images = json.loads(args.images)
    idl = json.loads((args.root / 'evidence/upstream/pump.json').read_text())
    assert idl['address'] == str(PROGRAM)
    for name, disc in IX.items():  # discriminators in this file must match the upstream IDL
        assert bytes(next(i['discriminator'] for i in idl['instructions'] if i['name'] == name)) == disc
    for a in idl['accounts']:
        if a['name'] in DISC:
            assert bytes(a['discriminator']) == DISC[a['name']]
    cases = plan()
    blobs = {n: Path(images[n]).read_bytes() for n in ('original', 'candidate')}
    runtime = args.out / 'runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    for old in runtime.glob('*'):
        old.unlink()
    write_gz(runtime / 'plan.json.gz', json.dumps(cases, sort_keys=True, indent=0) + '\n')
    report = {'scope': 'Pump Main multi_hop_curve_swap sent directly (pump_amm global_config PDA in its signer slot, signature verification off); FeeConfig read as account data (no CPI); original vs rebuild under the upgradeable loader; synthetic state; no network.',
              'images': {n: hashlib.sha256(b).hexdigest() for n, b in blobs.items()},
              'image_bytes': {n: len(b) for n, b in blobs.items()},
              'image_bytes_difference_div_250': (len(blobs['original']) - len(blobs['candidate'])) / 250,
              'behavior_fields': list(BEHAVIOR), 'loaders': {}, 'receipts': {}}
    for loader in LOADERS:
        original = run_plan(images['original'], loader, cases)
        candidate = run_plan(images['candidate'], loader, cases)
        lines = []
        for ro, rc in zip(original, candidate):
            lines += [json.dumps({'loader': loader, 'image': 'original', **ro}, sort_keys=True, separators=(',', ':')),
                      json.dumps({'loader': loader, 'image': 'candidate', **rc}, sort_keys=True, separators=(',', ':'))]
        name = f'receipts-{loader}.jsonl.gz'
        write_gz(runtime / name, '\n'.join(lines) + '\n')
        report['receipts'][name] = {'count': len(lines),
                                    'sha256': hashlib.sha256((runtime / name).read_bytes()).hexdigest()}
        report['loaders'][loader] = summarize(cases, original, candidate)
    report['idl_sha256'] = hashlib.sha256((args.root / 'evidence/upstream/pump.json').read_bytes()).hexdigest()
    write_gz(runtime / 'report.json.gz', json.dumps(report, sort_keys=True, indent=1) + '\n')
    for loader, s in report['loaders'].items():
        print(loader, json.dumps({k: s[k] for k in ('case_count', 'behavior_mismatches', 'compute_units_equal_cases',
                                                    'logs_equal_cases', 'cases_by_stop', 'compute_unit_delta_by_stop',
                                                    'log_difference_kinds')}, indent=1))


if __name__ == '__main__':
    main()
