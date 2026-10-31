"""Captured-program checks for Pump `claim_token_incentives` on Token-2022 mints.

Every case runs `claim_token_incentives` from the captured
`evidence/original/pump/deployed.so` on LiteSVM, with the captured SPL Token,
Token-2022 and Associated Token programs, against a synthetic incentive
schedule, an incentive mint with Token-2022 extensions, and both token accounts
in the shapes the instruction has to refuse. The same inputs go to
`programs/pump/recovered/token_incentives_token2022_host.rs`, and the error,
token movements, withheld amount, created user account, stored user accumulator
and emitted event must agree. This shows matching behavior on these inputs only;
it is not a byte-identity claim.
"""
from pathlib import Path
import base64
import hashlib
import json
import random
import re
import struct
import subprocess
import tempfile
import unittest

from solders.account import Account
from solders.clock import Clock
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.litesvm import LiteSVM
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from solders.transaction_metadata import FailedTransactionMetadata

ROOT = Path(__file__).resolve().parents[1]
PUMP_ELF = ROOT / 'evidence/original/pump/deployed.so'
TOKEN_ELF = ROOT / 'evidence/dependencies/spl_token/deployed.so'
TOKEN22_ELF = ROOT / 'evidence/dependencies/spl_token_2022/deployed.so'
ATA_ELF = ROOT / 'evidence/dependencies/associated_token/deployed.so'
ELF_SHA256 = {
    PUMP_ELF: '7a19affaa2c6187e04a5fe0ea298cee81fa5eb8c24cfcc30d85f615e89f7b02d',
    TOKEN_ELF: '8190d3f7ceb6cb7a7a8d8924bff89f9f611e15ce1f806f2b6237f3311a98f697',
    TOKEN22_ELF: '15a2e615a42e20f31714bbaaee43002ae6f1cda2e8d7118243117ab3c1342e2d',
    ATA_ELF: '6804554e69fd3a58caa191dc4a58f4c67223d30ca28ab8987f39fc18d2f7374d',
}
HOST_SOURCE = ROOT / 'programs/pump/recovered/token_incentives_token2022_host.rs'

IDL = json.loads((ROOT / 'evidence/upstream/pump.json').read_text(encoding='utf-8'))
PUMP = Pubkey.from_string(IDL['address'])
TOKEN = Pubkey.from_string('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA')
TOKEN22 = Pubkey.from_string('TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb')
ATA = Pubkey.from_string('ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL')
SYSTEM = Pubkey.default()
ACCOUNT_DISC = {a['name']: bytes(a['discriminator']) for a in IDL['accounts']}
IX = next(i for i in IDL['instructions'] if i['name'] == 'claim_token_incentives')
EVENT_DISC = next(bytes(e['discriminator']) for e in IDL['events'] if e['name'] == 'ClaimTokenIncentivesEvent')

PAYER = Keypair.from_seed(bytes([231]) * 32)
USER = Pubkey.from_bytes(bytes([41]) * 32)  # not a signer
MINT = Pubkey.from_bytes(bytes([42]) * 32)
STRANGER = Pubkey.from_bytes(bytes([43]) * 32)
WRONG_ATA = Pubkey.from_bytes(bytes([44]) * 32)
PROGRAMS = {'t22': TOKEN22, 'spl': TOKEN, 'system': SYSTEM}


def pda(*seeds):
    return Pubkey.find_program_address(list(seeds), PUMP)[0]


GLOBAL_VOLUME = pda(b'global_volume_accumulator')
USER_VOLUME = pda(b'user_volume_accumulator', bytes(USER))
EVENT_AUTHORITY = pda(b'__event_authority')
U64 = 2**64 - 1
DAY = 86_400
START = 1_700_000_000
NOW = START + 3 * DAY + 5
FEE_250 = (0, 0, 0, 250, 10**18)
# 7e9 of 3e10 sol volume on a 1e12 day.
DUE = 233_333_333_333


def ata(owner, program):
    return Pubkey.find_program_address([bytes(owner), bytes(program), bytes(MINT)], ATA)[0]


def rent(size):
    return (128 + size) * 6960


def tlv(kind, body=b''):
    return struct.pack('<HH', kind, len(body)) + body


def mint_data(item):
    base = (struct.pack('<I', 0) + bytes(32) + struct.pack('<Q', U64) + bytes([item['decimals'], 1])
            + struct.pack('<I', 0) + bytes(32))
    if item['mint_truncated']:
        return base[:40]
    ext = b''
    if item['fee']:
        older_bps, older_max, newer_epoch, newer_bps, newer_max = item['fee']
        ext += tlv(1, bytes(72) + struct.pack('<QQH', 0, older_max, older_bps)
                   + struct.pack('<QQH', newer_epoch, newer_max, newer_bps))
    if item['hook_set']:
        ext += tlv(14, bytes(32) + bytes([7]) * 32)
    if item['paused']:
        ext += tlv(26, bytes(32) + b'\1')
    if item['mint_non_transferable']:
        ext += tlv(9)
    if item['default_frozen']:
        ext += tlv(6, b'\2')
    return base.ljust(165, b'\0') + bytes([1]) + ext if ext else base


HOLDING = dict(balance=0, frozen=False, fee_extension=None, owner_matches=True, mint_matches=True, memo=False,
               cpi_guard=False, non_transferable=False, hook_extension=False, wrong_program=False)


def holding(**changes):
    return dict(HOLDING, **changes)


def token_data(holder, owner, fallback_fee_extension):
    held = HOLDING if isinstance(holder, str) else holder
    fee_extension = fallback_fee_extension if held['fee_extension'] is None else held['fee_extension']
    data = (bytes(MINT if held['mint_matches'] else STRANGER) + bytes(owner if held['owner_matches'] else STRANGER)
            + struct.pack('<Q', held['balance']) + struct.pack('<I', 0) + bytes(32)
            + bytes([0 if holder == 'uninitialized' else 2 if held['frozen'] else 1])
            + struct.pack('<I', 0) + bytes(16) + struct.pack('<I', 0) + bytes(32))
    ext = b''
    if fee_extension:
        ext += tlv(2, bytes(8))
    if held['memo']:
        ext += tlv(8, b'\1')
    if held['cpi_guard']:
        ext += tlv(11, b'\1')
    if held['non_transferable']:
        ext += tlv(13)
    if held['hook_extension']:
        ext += tlv(15, b'\0')
    data = data + bytes([2]) + ext if ext else data
    return data[:100] if holder == 'truncated' else data


USER_FIELDS = ('needs_claim', 'unclaimed', 'claimed', 'volume', 'last_update', 'has_claimed')


def global_volume_data(item):
    supply, volumes = [0] * 30, [0] * 30
    supply[1], volumes[1] = 10**12, 3 * 10**10
    return (ACCOUNT_DISC['GlobalVolumeAccumulator'] + struct.pack('<qqq', START, START + 20 * DAY, DAY)
            + bytes(MINT if item['global_mint_ok'] else STRANGER) + struct.pack('<30Q', *supply) + struct.pack('<30Q', *volumes))


def user_volume_data(item):
    data = bytearray(137)
    data[:8] = ACCOUNT_DISC['UserVolumeAccumulator']
    data[8:40] = bytes(USER)
    struct.pack_into('<?QQQq?', data, 40, *(item[k] for k in USER_FIELDS))
    struct.pack_into('<Q', data, 74, 999)  # cashback_earned: must be left alone
    return bytes(data)


def read_user(data):
    assert data[8:40] == bytes(USER) and struct.unpack_from('<Q', data, 74)[0] == 999
    values = struct.unpack_from('<?QQQq?', data, 40)
    return dict(zip(USER_FIELDS, (int(v) if isinstance(v, bool) else v for v in values)))


DEFAULTS = dict(now=NOW, epoch=0, needs_claim=True, unclaimed=0, claimed=0, volume=7 * 10**9, last_update=START + DAY + 9,
                has_claimed=False, token_program='t22', mint_owner='t22', global_mint_ok=True, mint_truncated=False,
                decimals=6, fee=None, hook_set=False, paused=False, mint_non_transferable=False, default_frozen=False,
                vault=None, vault_address_ok=True, user_ata=None, user_address_ok=True)


def case(**changes):
    item = dict(DEFAULTS, **changes)
    if item['vault'] is None:
        item['vault'] = holding(balance=10**15)
    if item['user_ata'] is None:
        item['user_ata'] = holding(balance=3)
    return item


def host_ata(item, held):
    if isinstance(held, str):
        return held
    fee_extension = bool(item['fee']) if held['fee_extension'] is None else held['fee_extension']
    text = ':'.join(str(int(v)) for v in (held['balance'], held['frozen'], fee_extension, held['owner_matches'],
                                          held['mint_matches'], held['memo'], held['cpi_guard'], held['non_transferable'],
                                          held['hook_extension']))
    return 'wrong:' + text if held['wrong_program'] else text


def host_line(item):
    fee = ':'.join(str(v) for v in item['fee']) if item['fee'] else '-'
    fields = [item['now'], item['epoch'], int(item['needs_claim']), item['unclaimed'], item['claimed'], item['volume'],
              item['last_update'], int(item['has_claimed']), item['token_program'], item['mint_owner'],
              int(item['global_mint_ok']), int(item['mint_truncated']), fee, int(item['hook_set']), int(item['paused']),
              int(item['mint_non_transferable']), int(item['default_frozen']), host_ata(item, item['vault']),
              int(item['vault_address_ok']), host_ata(item, item['user_ata']), int(item['user_address_ok'])]
    return ','.join(str(f) for f in fields)


def error_name(text):
    code = re.search(r'Custom\((\d+)\)', text)
    if code:
        return f'error:{code.group(1)}'
    name = re.search(r'Fieldless\((\w+)\)', text)
    return name.group(1) if name else text


def account_extensions(data):
    found = {}
    offset = 166
    while offset + 4 <= len(data):
        kind, length = struct.unpack_from('<HH', data, offset)
        if kind == 0:
            break
        found[kind] = data[offset + 4:offset + 4 + length]
        offset += 4 + length
    return found


class Chain:
    """One VM for every case: reloading the ELFs costs far more than a transaction."""

    def __init__(self):
        self.vm = LiteSVM().with_sigverify(True).with_transaction_history(0)
        for key, path in ((PUMP, PUMP_ELF), (TOKEN, TOKEN_ELF), (TOKEN22, TOKEN22_ELF), (ATA, ATA_ELF)):
            self.vm.add_program_from_file(key, path)
        self.stale = set()

    def run(self, item):
        vm = self.vm
        vm.set_clock(Clock(100, item['now'], item['epoch'], 0, item['now']))
        for key in self.stale:
            vm.set_account(key, Account(0, b'', SYSTEM))
        program = PROGRAMS[item['token_program']]
        token_owner = TOKEN if program == TOKEN else TOKEN22
        vault_key = ata(GLOBAL_VOLUME, program) if item['vault_address_ok'] else WRONG_ATA
        user_key = ata(USER, program) if item['user_address_ok'] else STRANGER
        accounts = {PAYER.pubkey(): Account(10**12, b'', SYSTEM),
                    MINT: Account(10**10, mint_data(item), PROGRAMS[item['mint_owner']]),
                    GLOBAL_VOLUME: Account(10**9, global_volume_data(item), PUMP),
                    USER_VOLUME: Account(10**9, user_volume_data(item), PUMP)}
        for key, holder, authority in ((vault_key, item['vault'], GLOBAL_VOLUME), (user_key, item['user_ata'], USER)):
            if holder == 'missing':
                continue
            wrong = not isinstance(holder, str) and holder['wrong_program']
            accounts[key] = Account(10**8, token_data(holder, authority, bool(item['fee'])),
                                    (TOKEN if token_owner == TOKEN22 else TOKEN22) if wrong else token_owner)
        for key, account in accounts.items():
            vm.set_account(key, account)
        self.stale = {k for k in accounts if k != PAYER.pubkey()} | {vault_key, user_key}
        named = {'user': USER, 'user_ata': user_key, 'global_volume_accumulator': GLOBAL_VOLUME,
                 'global_incentive_token_account': vault_key, 'user_volume_accumulator': USER_VOLUME, 'mint': MINT,
                 'token_program': program, 'system_program': SYSTEM, 'associated_token_program': ATA,
                 'event_authority': EVENT_AUTHORITY, 'program': PUMP, 'payer': PAYER.pubkey()}
        metas = [AccountMeta(named[a['name']], a.get('signer', False), a.get('writable', False)) for a in IX['accounts']]

        def data(key):
            account = vm.get_account(key)
            return bytes(account.data) if account else b''

        def tokens(key):
            raw = data(key)
            return struct.unpack_from('<Q', raw, 64)[0] if len(raw) >= 72 else 0

        before = (vm.get_account(PAYER.pubkey()).lamports, tokens(vault_key), tokens(user_key))
        existed = vm.get_account(user_key) is not None and vm.get_account(user_key).owner != SYSTEM
        tx = Transaction.new_signed_with_payer([Instruction(PUMP, bytes(IX['discriminator']), metas)], PAYER.pubkey(),
                                               [PAYER], vm.latest_blockhash())
        result = vm.send_transaction(tx)
        if isinstance(result, FailedTransactionMetadata):
            if any('panicked' in line for line in result.meta().logs()):
                return {'error': 'panic'}
            return {'error': error_name(str(result.err()))}
        raw = data(user_key)
        return {'error': None, 'paid': before[0] - vm.get_account(PAYER.pubkey()).lamports - 5_000,
                'vault_tokens': tokens(vault_key) - before[1], 'user_tokens': tokens(user_key) - before[2],
                'user_ata_created': not existed, 'user_ata_len': len(raw), 'user_ata_state': raw[108],
                'withheld': struct.unpack('<Q', account_extensions(raw).get(2, bytes(8)))[0],
                'user': read_user(data(USER_VOLUME)),
                'events': [base64.b64decode(line[14:]) for line in result.logs() if line.startswith('Program data: ')]}


def with_faults(*faults):
    merged = dict(vault=dict(balance=10**15), user_ata=dict(balance=3))
    extra = {}
    for fault in faults:
        for key, value in fault.items():
            if key in merged and isinstance(value, dict):
                merged[key] = dict(merged[key], **value)
            else:
                extra[key] = value
    args = dict(vault=holding(**merged['vault']), user_ata=holding(**merged['user_ata']))
    args.update(extra)
    return case(**args)


def fixed_cases():
    cases = []
    add = lambda **k: cases.append(case(**k))
    for fee in (None, FEE_250):
        for user_ata in (None, 'missing'):
            add(fee=fee, user_ata=user_ata)
            # Nothing to claim: no transfer and no event, but a missing user account is still created.
            add(fee=fee, user_ata=user_ata, volume=0)
            add(fee=fee, user_ata=user_ata, volume=0, vault=holding(balance=0))
            add(fee=fee, user_ata=user_ata, volume=0, paused=True)
            add(fee=fee, user_ata=user_ata, volume=0, hook_set=True)
            add(fee=fee, user_ata=user_ata, volume=0, mint_non_transferable=True)
            add(fee=fee, user_ata=user_ata, volume=0, default_frozen=True)
            add(fee=fee, user_ata=user_ata, volume=0, vault=holding(balance=5, frozen=True))
            add(fee=fee, user_ata=user_ata, unclaimed=5, claimed=11, has_claimed=True)
            add(fee=fee, user_ata=user_ata, hook_set=True)
            add(fee=fee, user_ata=user_ata, paused=True)
            add(fee=fee, user_ata=user_ata, mint_non_transferable=True)
            add(fee=fee, user_ata=user_ata, default_frozen=True)
            add(fee=fee, user_ata=user_ata, paused=True, hook_set=True, default_frozen=True)
            add(fee=fee, user_ata=user_ata, claimed=U64 - DUE)
            add(fee=fee, user_ata=user_ata, claimed=U64 - DUE + 1)
            add(fee=fee, user_ata=user_ata, claimed=U64, vault=holding(balance=10**15, frozen=True))
            add(fee=fee, user_ata=user_ata, vault=holding(balance=DUE))
            add(fee=fee, user_ata=user_ata, vault=holding(balance=DUE - 1))
            add(fee=fee, user_ata=user_ata, vault=holding(balance=DUE - 1, frozen=True))
            add(fee=fee, user_ata=user_ata, vault=holding(balance=DUE - 1, non_transferable=True))
            add(fee=fee, user_ata=user_ata, vault=holding(balance=DUE - 1, cpi_guard=True))
            add(fee=fee, user_ata=user_ata, vault=holding(balance=DUE - 1), paused=True)
            add(fee=fee, user_ata=user_ata, vault=holding(balance=DUE - 1), hook_set=True)
            # A failing transfer undoes the rollover; a schedule panic wins over token failures.
            add(fee=fee, user_ata=user_ata, now=START + 31 * DAY, vault=holding(balance=10**15, frozen=True))
        # Accounts before the handler.
        for vault_shape in ('missing', 'truncated', 'uninitialized', holding(balance=10**15, wrong_program=True),
                            holding(balance=10**15, owner_matches=False), holding(balance=10**15, mint_matches=False)):
            add(fee=fee, vault=vault_shape)
            add(fee=fee, vault=vault_shape, volume=0)
            add(fee=fee, vault=vault_shape, user_ata='missing')
            add(fee=fee, vault=vault_shape, user_ata=holding(owner_matches=False))
            add(fee=fee, vault=vault_shape, global_mint_ok=False)
            add(fee=fee, vault=vault_shape, vault_address_ok=False)
        for user_shape in ('truncated', 'uninitialized', holding(balance=3, wrong_program=True),
                           holding(balance=3, owner_matches=False), holding(balance=3, mint_matches=False)):
            add(fee=fee, user_ata=user_shape)
            add(fee=fee, user_ata=user_shape, volume=0)
            add(fee=fee, user_ata=user_shape, global_mint_ok=False)
            add(fee=fee, user_ata=user_shape, user_address_ok=False)
            add(fee=fee, user_ata=user_shape, vault_address_ok=False)
        add(fee=fee, vault_address_ok=False)
        add(fee=fee, vault_address_ok=False, volume=0)
        add(fee=fee, user_address_ok=False)
        add(fee=fee, user_address_ok=False, volume=0)
        add(fee=fee, user_address_ok=False, user_ata='missing')
        add(fee=fee, user_address_ok=False, user_ata='missing', volume=0)
        add(fee=fee, global_mint_ok=False)
        add(fee=fee, global_mint_ok=False, user_ata='missing')
        add(fee=fee, mint_truncated=True)
        add(fee=fee, mint_truncated=True, user_ata='missing')
        add(fee=fee, mint_truncated=True, global_mint_ok=False)
        add(fee=fee, mint_owner='system')
        add(fee=fee, mint_owner='system', user_ata='missing')
        add(fee=fee, mint_owner='system', global_mint_ok=False)
        add(fee=fee, token_program='system', mint_owner='t22')
        add(fee=fee, token_program='system', mint_owner='system')
        add(fee=fee, token_program='system', mint_owner='t22', global_mint_ok=False)
        add(fee=fee, token_program='spl', mint_owner='t22')
        add(fee=fee, token_program='spl', mint_owner='t22', user_ata='missing')
        add(fee=fee, token_program='spl', mint_owner='t22', vault=holding(balance=10**15, wrong_program=True))
        add(fee=fee, mint_owner='spl')
        add(fee=fee, mint_owner='spl', user_ata='missing')
    # SPL Token mint and accounts through the same interface, and mixed owners.
    for mint_owner in ('spl', 't22'):
        spl = dict(token_program='spl', mint_owner=mint_owner)
        add(**spl)
        add(**spl, volume=0)
        add(**spl, user_ata='missing')
        add(**spl, user_ata='missing', volume=0)
        add(**spl, user_ata='missing', user_address_ok=False)
        add(**spl, vault=holding(balance=DUE - 1))
        add(**spl, vault=holding(balance=DUE))
        add(**spl, vault=holding(balance=10**15, frozen=True))
        add(**spl, vault=holding(balance=DUE - 1, frozen=True))
        add(**spl, vault=holding(balance=10**15, mint_matches=False))
        add(**spl, vault=holding(balance=DUE - 1, mint_matches=False))
        add(**spl, user_ata=holding(balance=3, frozen=True))
        add(**spl, user_ata=holding(balance=3, frozen=True), vault=holding(balance=DUE - 1))
        add(**spl, user_ata=holding(balance=3, frozen=True), vault=holding(balance=10**15, mint_matches=False))
        add(**spl, user_ata=holding(balance=3, mint_matches=False))
        add(**spl, claimed=U64, vault=holding(balance=DUE - 1))
        add(**spl, claimed=U64)
    add(mint_owner='spl', user_ata='missing', user_address_ok=False)
    add(mint_owner='spl', user_ata='missing', global_mint_ok=False)
    # A hook mint: both accounts must carry the hook account extension, and the claim still fails.
    for vault_hook in (False, True):
        for user_hook in (False, True):
            add(hook_set=True, vault=holding(balance=10**15, hook_extension=vault_hook),
                user_ata=holding(balance=3, hook_extension=user_hook))
            add(hook_set=True, volume=0, vault=holding(balance=10**15, hook_extension=vault_hook),
                user_ata=holding(balance=3, hook_extension=user_hook))
        add(hook_set=True, vault=holding(balance=10**15, hook_extension=vault_hook), user_ata='missing')
        add(hook_set=True, volume=0, vault=holding(balance=10**15, hook_extension=vault_hook), user_ata='missing')
        add(hook_set=True, fee=FEE_250, vault=holding(balance=10**15, hook_extension=vault_hook), user_ata='missing')
        add(hook_set=False, vault=holding(balance=10**15, hook_extension=vault_hook), user_ata=holding(balance=3, hook_extension=True))
    # Transfer fee: schedule choice, rounding, cap, whole amount.
    for fee, epoch in ((FEE_250, 0), ((0, 0, 0, 250, 100), 0), ((0, 0, 0, 10_000, 10**18), 0), ((100, 10**18, 5, 250, 10**18), 4),
                       ((100, 10**18, 5, 250, 10**18), 5), ((100, 10**18, 5, 250, 10**18), 6), ((100, 17, 5, 250, 10**18), 1),
                       ((0, 0, 0, 0, 10**18), 0), ((0, 0, 0, 250, 0), 0)):
        add(fee=fee, epoch=epoch)
        add(fee=fee, epoch=epoch, user_ata='missing')
        add(fee=fee, epoch=epoch, volume=0, unclaimed=U64, vault=holding(balance=U64), user_ata=holding(balance=0))
    for amount in (1, 39, 40, 41, 79, 80, 81, 400, 401, 10**9):
        add(fee=FEE_250, volume=0, unclaimed=amount)
        add(fee=FEE_250, volume=0, unclaimed=amount, user_ata=holding(balance=3, fee_extension=False))
    add(fee=(0, 0, 0, 0, 10**18), user_ata=holding(balance=3, fee_extension=False))
    add(fee=(0, 0, 0, 250, 0), user_ata=holding(balance=3, fee_extension=False))
    add(fee=FEE_250, vault=holding(balance=10**15, fee_extension=False))
    add(fee=FEE_250, vault=holding(balance=10**15, fee_extension=False), user_ata='missing')
    # Order of the checks, pair by pair.
    faults = {
        'vault_frozen': dict(vault=dict(frozen=True)), 'vault_short': dict(vault=dict(balance=DUE - 1)),
        'non_transferable': dict(vault=dict(non_transferable=True)), 'mint_non_transferable': dict(mint_non_transferable=True),
        'paused': dict(paused=True), 'cpi_guard': dict(vault=dict(cpi_guard=True)),
        'user_frozen': dict(user_ata=dict(frozen=True)), 'memo': dict(user_ata=dict(memo=True)),
        'no_fee_extension': dict(fee=FEE_250, user_ata=dict(fee_extension=False)), 'hook': dict(hook_set=True),
        'vault_owner': dict(vault=dict(owner_matches=False)), 'vault_mint': dict(vault=dict(mint_matches=False)),
        'vault_program': dict(vault=dict(wrong_program=True)), 'vault_address': dict(vault_address_ok=False),
        'user_owner': dict(user_ata=dict(owner_matches=False)), 'user_mint': dict(user_ata=dict(mint_matches=False)),
        'user_program': dict(user_ata=dict(wrong_program=True)), 'user_address': dict(user_address_ok=False),
        'global_mint': dict(global_mint_ok=False), 'mint_short': dict(mint_truncated=True),
        'mint_owner': dict(mint_owner='system'), 'mint_program': dict(mint_owner='spl'),
        'token_program': dict(token_program='system'),
    }
    names = list(faults)
    for i, left in enumerate(names):
        cases.append(with_faults(faults[left]))
        for right in names[i + 1:]:
            cases.append(with_faults(faults[left], faults[right]))
    return cases


def random_cases(count=400, seed=2310):
    rng = random.Random(seed)
    cases = []

    def fee():
        if rng.random() < 0.4:
            return None
        return (rng.randrange(0, 10_001), rng.choice((0, rng.randrange(0, 10**6), U64)), rng.randrange(0, 8),
                rng.randrange(0, 10_001), rng.choice((0, rng.randrange(0, 10**6), U64)))

    def held(vault):
        if rng.random() < 0.06:
            return rng.choice(('missing', 'truncated', 'uninitialized'))
        flag = lambda p: rng.random() < p
        balance = rng.choice((DUE, DUE - 1, 10**15, rng.randrange(0, 10**12))) if vault else rng.randrange(0, 10**6)
        return holding(balance=balance, frozen=flag(0.05), fee_extension=None if flag(0.9) else flag(0.5),
                       owner_matches=not flag(0.04), mint_matches=not flag(0.04), memo=flag(0.05), cpi_guard=flag(0.05),
                       non_transferable=flag(0.05), hook_extension=flag(0.3), wrong_program=flag(0.03))

    for _ in range(count):
        user_ata = 'missing' if rng.random() < 0.3 else held(False)
        cases.append(case(fee=fee(), epoch=rng.randrange(0, 8), hook_set=rng.random() < 0.08, paused=rng.random() < 0.08,
                          mint_non_transferable=rng.random() < 0.06, default_frozen=rng.random() < 0.08,
                          decimals=rng.randrange(0, 12), vault=held(True), user_ata=user_ata,
                          vault_address_ok=rng.random() > 0.03, user_address_ok=rng.random() > 0.03,
                          global_mint_ok=rng.random() > 0.03, mint_truncated=rng.random() < 0.03,
                          mint_owner=rng.choice(('t22',) * 28 + ('system', 'spl')),
                          unclaimed=rng.choice((0, rng.randrange(0, 10**12))), volume=rng.choice((0, rng.randrange(0, 10**11))),
                          claimed=rng.choice((0, rng.randrange(0, 10**12), U64 - rng.randrange(0, 10**12))),
                          has_claimed=rng.random() < 0.5))
    return cases


def decode_event(data):
    assert data[:8] == EVENT_DISC and data[8:40] == bytes(USER) and data[40:72] == bytes(MINT)
    return struct.unpack_from('<QqQQ', data, 72)


class TokenIncentivesToken2022CapturedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in ELF_SHA256.items():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path
        cls.tmp = tempfile.TemporaryDirectory()
        host = Path(cls.tmp.name) / 'token-incentives-token2022-host'
        subprocess.run(['rustc', '--edition=2021', '-O', '-D', 'warnings', str(HOST_SOURCE), '-o', str(host)], check=True)
        cls.host = host
        cls.chain = Chain()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def host_answers(self, cases):
        text = ''.join(host_line(item) + '\n' for item in cases)
        out = subprocess.run([str(self.host)], input=text, capture_output=True, text=True, check=True).stdout
        return out.splitlines()

    def assert_matches(self, item, answer, captured):
        if not answer.startswith('ok,'):
            self.assertEqual(captured['error'], answer)
            return
        self.assertIsNone(captured['error'])
        amount, kept, size, state, *fields = map(int, answer.split(',')[1:])
        user = dict(zip(USER_FIELDS, fields))
        self.assertEqual(captured['user'], user)
        self.assertEqual(captured['vault_tokens'], -amount)
        self.assertEqual(captured['user_tokens'], amount - kept)
        self.assertEqual(captured['withheld'], kept)
        self.assertEqual(captured['user_ata_created'], size != 0)
        self.assertEqual(captured['paid'], rent(size) if size else 0)
        if size:
            self.assertEqual((captured['user_ata_len'], captured['user_ata_state']), (size, state))
        expected = [(amount, item['now'], user['claimed'], user['volume'])] if amount else []
        self.assertEqual([decode_event(e) for e in captured['events']], expected)

    def run_cases(self, cases):
        answers = self.host_answers(cases)
        self.assertEqual(len(answers), len(cases))
        for item, answer in zip(cases, answers):
            with self.subTest(case=host_line(item), host=answer):
                self.assert_matches(item, answer, self.chain.run(item))

    def test_fixed_cases_match_captured_program(self):
        self.run_cases(fixed_cases())

    def test_seeded_random_cases_match_captured_program(self):
        self.run_cases(random_cases())

    def test_checker_rejects_a_wrong_withheld_amount(self):
        item = case(fee=FEE_250, user_ata='missing')
        answer = self.host_answers([item])[0]
        captured = self.chain.run(item)
        self.assert_matches(item, answer, captured)
        for broken in (dict(captured, withheld=captured['withheld'] + 1),
                       dict(captured, user_tokens=captured['user_tokens'] + 1),
                       dict(captured, paid=captured['paid'] - 1),
                       dict(captured, user_ata_created=False),
                       dict(captured, user=dict(captured['user'], claimed=0))):
            with self.assertRaises(AssertionError):
                self.assert_matches(item, answer, broken)

    def test_fixed_cases_cover_every_outcome(self):
        answers = self.host_answers(fixed_cases())
        outcomes = {a.split(',')[0] for a in answers}
        self.assertEqual(outcomes, {
            'ok', 'panic', 'InvalidAccountData', 'UninitializedAccount', 'IncorrectProgramId', 'MissingAccount', 'error:1',
            'error:3', 'error:13', 'error:17', 'error:36', 'error:37', 'error:42', 'error:67', 'error:2009', 'error:2014',
            'error:2015', 'error:2023', 'error:3007', 'error:3008', 'error:3012', 'error:3014', 'error:6039',
        })


if __name__ == '__main__':
    unittest.main()
