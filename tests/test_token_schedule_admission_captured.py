"""Captured-program checks for the account admission of `admin_update_token_incentives`.

Every case runs `admin_update_token_incentives` from the captured
`evidence/original/pump/deployed.so` on LiteSVM, with the captured SPL Token and
Associated Token programs. One account set is the expected one from
`tests/test_token_schedule_captured.py`. A case changes it by one, two or three
faults: wrong address, owner, data, mutability or program.

The same faults go to `programs/pump/recovered/token_schedule_admission_host.rs`,
and the error, or the event count and the stored mint, must agree. The schedule
itself belongs to `token_schedule.rs`. This shows matching behavior on these
inputs only; it is not a byte-identity claim.
"""
from pathlib import Path
import hashlib
import itertools
import random
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from solders.account import Account
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.litesvm import LiteSVM
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from solders.transaction_metadata import FailedTransactionMetadata

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_token_schedule_captured as base  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ELF_SHA256 = base.ELF_SHA256
HOST_SOURCE = ROOT / 'programs/pump/recovered/token_schedule_admission_host.rs'

ALIEN = Pubkey.from_bytes(bytes([62]) * 32)
TOKEN22 = Pubkey.from_string('TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb')
FEE_PAYER = Keypair.from_seed(bytes([234]) * 32)
STRANGER = Keypair.from_seed(bytes([235]) * 32)
ROUTES = ('update',)
NAMES = [a['name'] for a in base.IX['accounts']]
SLOT_FAULTS = {
    'authority': ('unsigned', 'readonly', 'other'),
    'global': ('key', 'owner', 'short', 'disc', 'missing'),
    'global_volume_accumulator': ('key', 'readonly', 'owner', 'short', 'disc', 'trunc', 'missing'),
    'mint': ('key', 'owner', 'short', 'missing'),
    'global_incentive_token_account': ('key', 'readonly', 'owner', 'short', 'mintdata', 'ownerdata', 'frozen', 'missing',
                                       'funded'),
    'associated_token_program': ('key',),
    'system_program': ('key',),
    'token_program': ('key', 't22'),
    'event_authority': ('key',),
    'program': ('key', 'token'),
}
RUNTIME = {'InvalidAccountData': 'invalid_account_data', 'MissingAccount': 'missing_account',
           'PrivilegeEscalation': 'privilege_escalation'}


def faults_of():
    return [f'{slot}.{kind}' for slot in NAMES for kind in SLOT_FAULTS.get(slot, ())]


def rewrite(account, start, value):
    data = bytearray(bytes(account.data))
    data[start:start + len(value)] = value
    return Account(account.lamports, bytes(data), account.owner)


def error_name(result):
    text = str(result.err())
    code = re.search(r'Custom\((\d+)\)', text)
    if code:
        return f'error:{code.group(1)}'
    if any('panicked' in line for line in result.meta().logs()):
        return 'panic'
    for name, short in RUNTIME.items():
        if name in text:
            return f'error:{short}'
    return f'error:{text}'


class Harness:
    """One VM. Each run clears the last run's accounts and writes its own."""

    def __init__(self):
        self.vm = LiteSVM().with_sigverify(True).with_transaction_history(0)
        self.vm.add_program_from_file(base.PUMP, base.PUMP_ELF)
        self.vm.add_program_from_file(base.TOKEN, base.TOKEN_ELF)
        self.vm.add_program_from_file(base.ATA, base.ATA_ELF)
        self.vm.set_clock(base.Clock(100, base.NOW, 0, 0, base.NOW))
        self.stale = []

    def put(self, key, account):
        self.vm.set_account(key, account)
        self.stale.append(key)

    def run(self, route, faults):
        for key in self.stale:
            self.vm.set_account(key, Account(0, b'', base.SYSTEM))
        self.stale.clear()
        self.vm.expire_blockhash()
        self.put(FEE_PAYER.pubkey(), Account(10**12, b'', base.SYSTEM))
        item = base.case()
        authority = base.AUTHORITY
        keys = {'authority': authority.pubkey(), 'global': base.GLOBAL, 'global_volume_accumulator': base.GVA,
                'mint': base.MINT, 'global_incentive_token_account': base.GVA_ATA, 'associated_token_program': base.ATA,
                'system_program': base.SYSTEM, 'token_program': base.TOKEN, 'event_authority': base.EVENT_AUTHORITY,
                'program': base.PUMP}
        accounts = {
            authority.pubkey(): Account(10**12, b'', base.SYSTEM),
            STRANGER.pubkey(): Account(10**12, b'', base.SYSTEM),
            base.GLOBAL: Account(10**9, base.global_data(), base.PUMP),
            base.GVA: Account(10**9, base.gva_data(item), base.PUMP),
            base.MINT: Account(10**9, base.mint_data(), base.TOKEN),
            base.GVA_ATA: Account(base.TOKEN_RENT, base.token_data(base.MINT, base.GVA, 0), base.TOKEN),
        }
        read_only, unsigned = set(), False
        for fault in faults:
            slot, kind = fault.split('.')
            key = keys[slot]
            present = accounts.get(key)
            if kind == 'readonly':
                read_only.add(slot)
            elif kind == 'unsigned':
                unsigned = True
            elif kind == 'other':
                authority = STRANGER
                keys[slot] = STRANGER.pubkey()
            elif kind == 'key':
                keys[slot] = Pubkey.from_bytes(bytes([100 + NAMES.index(slot)]) * 32)
                if present:
                    accounts[keys[slot]] = accounts.pop(key)
            elif kind == 'token':
                keys[slot] = base.TOKEN
            elif kind == 't22':
                keys[slot] = TOKEN22
            elif kind == 'missing':
                accounts.pop(key, None)
            elif kind == 'funded':
                # A system account with lamports where the token account belongs.
                accounts[key] = Account(10**7, b'', base.SYSTEM)
            elif present is None:
                continue
            elif kind == 'owner':
                accounts[key] = Account(present.lamports, bytes(present.data), ALIEN)
            elif kind == 'short':
                accounts[key] = Account(present.lamports, bytes(4), present.owner)
            elif kind == 'trunc':
                accounts[key] = Account(present.lamports, bytes(present.data)[:8], present.owner)
            elif kind == 'disc':
                accounts[key] = rewrite(present, 0, bytes(8))
            elif len(present.data) == 165:
                value = {'mintdata': (0, bytes([9]) * 32), 'ownerdata': (32, bytes([9]) * 32), 'frozen': (108, b'\x02')}
                accounts[key] = rewrite(present, *value[kind])
        for key, account in accounts.items():
            self.put(key, account)
        metas = [AccountMeta(keys[a['name']], a.get('signer', False) and not unsigned,
                             a.get('writable', False) and a['name'] not in read_only) for a in base.IX['accounts']]
        signers = [FEE_PAYER] if unsigned else [FEE_PAYER, authority]
        tx = Transaction.new_signed_with_payer([Instruction(base.PUMP, bytes(base.IX['discriminator']) + base.args(item), metas)],
                                               FEE_PAYER.pubkey(), signers, self.vm.latest_blockhash())
        result = self.vm.send_transaction(tx)
        if isinstance(result, FailedTransactionMetadata):
            return error_name(result)
        events = sum(1 for line in result.logs() if line.startswith('Program data: '))
        stored = bytes(self.vm.get_account(keys['global_volume_accumulator']).data)[32:64]
        token = self.vm.get_account(keys['global_incentive_token_account'])
        return f"ok,{events},{int(stored == bytes(keys['mint']))},{len(token.data)}"


def single_cases():
    return [(route, (fault,)) for route in ROUTES for fault in faults_of()] + [(route, ()) for route in ROUTES]


def pair_cases():
    return [(route, pair) for route in ROUTES for pair in itertools.combinations(faults_of(), 2)]


def triple_cases(count=1000, seed=3521):
    rng = random.Random(seed)
    faults = faults_of()
    # In the list's order, as the pairs are: a slot's later fault wins.
    return [(ROUTES[0], tuple(faults[i] for i in sorted(rng.sample(range(len(faults)), 3)))) for _ in range(count)]


def host_line(route, faults):
    return ' '.join((route,) + faults)


class TokenScheduleAdmissionCapturedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in ELF_SHA256.items():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path
        cls.tmp = tempfile.TemporaryDirectory()
        host = Path(cls.tmp.name) / 'token-schedule-admission-host'
        subprocess.run(['rustc', '--edition=2021', '-O', '-D', 'warnings', str(HOST_SOURCE), '-o', str(host)], check=True)
        cls.host = host
        cls.harness = Harness()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def host_answers(self, cases):
        text = ''.join(host_line(*case) + '\n' for case in cases)
        return subprocess.run([str(self.host)], input=text, capture_output=True, text=True, check=True).stdout.splitlines()

    def run_cases(self, cases):
        answers = self.host_answers(cases)
        self.assertEqual(len(answers), len(cases))
        wrong = []
        for case, answer in zip(cases, answers):
            captured = self.harness.run(*case)
            if captured != answer:
                wrong.append((case, answer, captured))
        self.assertEqual(wrong[:40], [], f'{len(wrong)} of {len(cases)} differ')

    def test_single_faults_match_captured_program(self):
        self.run_cases(single_cases())

    def test_fault_pairs_match_captured_program(self):
        self.run_cases(pair_cases())

    def test_seeded_triples_match_captured_program(self):
        self.run_cases(triple_cases())

    def test_checker_rejects_a_changed_answer(self):
        # Negative control: run_cases must fail when the host's answer changes.
        answers = self.host_answers
        for changed in ('error:2000', 'ok,0,1,165'):
            with mock.patch.object(self, 'host_answers', lambda cases: [changed] * len(cases)):
                with self.assertRaises(AssertionError):
                    self.run_cases([('update', ())])
        self.assertEqual(answers([('update', ())]), [self.harness.run('update', ())])

    def test_cases_reach_every_stop(self):
        answers = set(self.host_answers(single_cases() + pair_cases()))
        self.assertEqual({a for a in answers if a.startswith('error:')},
                         {f'error:{c}' for c in (2000, 2006, 2014, 2015, 2023, 3001, 3002, 3003, 3007, 3008, 3010, 3012,
                                                 3014, 6000)}
                         | {'error:invalid_account_data', 'error:missing_account', 'error:privilege_escalation'})
        self.assertIn('ok,1,1,165', answers)


if __name__ == '__main__':
    unittest.main()
