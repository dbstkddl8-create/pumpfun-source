"""A receipt report's per-case rows must agree with the report header.

`research/pump-plain-receipts/verify.py` trusted `mismatches` — the producer's
claim about the whole report — and never looked inside a row.  A producer that
stamped an empty header over rows whose `original` and `candidate` snapshots
disagree was accepted.  This test rewrites one row and the pins that protect it,
so the only check that can still refuse the packet is the row-level one.
"""
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'research/pump-plain-receipts'
SUCCESS = 'Retained eleven-producer before/after wire reports verified'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rewrite_packet(packet, mutation=None, producer="pump_create_control_differential"):
    """Make one row disagree in both stages, updating every pin around it.

    Both stages carry the same rewritten row, so the before/after comparison
    and the normalized whole-report comparison still agree: only a check that
    reads the row's own `original` and `candidate` can refuse the packet.
    """
    pins = json.loads((packet / 'receipt-files.json').read_text())
    for stage in ('before', 'after'):
        tar_path = packet / f'receipts/{stage}-reports.tar.gz'
        with tarfile.open(tar_path) as archive:
            members = {member.name: archive.extractfile(member).read()
                       for member in archive.getmembers()}
        summary = json.loads(members['summary.json'])
        script = next(name for name in summary['producers'] if Path(name).stem == producer)
        for label, filename in (('plain', 'report.json'), ('gzip', 'report.json.gz')):
            wire = members[f'{Path(script).stem}/{filename}']
            compressed = wire.startswith(b'\x1f\x8b')
            report = json.loads(gzip.decompress(wire) if compressed else wire)
            if mutation is None:
                report['cases'][0]['candidate'] = {'diverged': True}
            else:
                mutation(report['cases'][0])
            decoded = json.dumps(report).encode()
            wire = gzip.compress(decoded, mtime=0) if compressed else decoded
            members[f'{Path(script).stem}/{filename}'] = wire
            summary['producers'][script][label].update(wire_sha256=sha(wire),
                                                       decoded_sha256=sha(decoded))
        members['summary.json'] = json.dumps(summary).encode()
        with tarfile.open(tar_path, 'w:gz') as archive:
            for name, data in members.items():
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), 0o644
                archive.addfile(info, io.BytesIO(data))
        summary_path = packet / f'receipts/{stage}-summary.json'
        summary_path.write_text(json.dumps(summary))
        pins[f'receipts/{stage}-reports.tar.gz'] = sha(tar_path.read_bytes())
        pins[f'receipts/{stage}-summary.json'] = sha(summary_path.read_bytes())
    (packet / 'receipt-files.json').write_text(json.dumps(pins))


def run(packet):
    return subprocess.run([sys.executable, '-B', str(packet / 'verify.py')],
                          capture_output=True, text=True, timeout=300)


class PlainReceiptCaseRowTests(unittest.TestCase):
    def test_row_that_disagrees_with_the_header_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            packet = Path(temporary) / 'pump-plain-receipts'
            shutil.copytree(PACKET, packet)
            rewrite_packet(packet)
            result = run(packet)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn(SUCCESS, result.stdout + result.stderr)
        self.assertIn('AssertionError', result.stderr)
        self.assertIn('pump_create_control_differential', result.stderr)

    def assert_mutation_refused(self, mutation, producer="pump_create_control_differential"):
        with tempfile.TemporaryDirectory() as temporary:
            packet = Path(temporary) / 'pump-plain-receipts'
            shutil.copytree(PACKET, packet)
            rewrite_packet(packet, mutation, producer)
            result = run(packet)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn(SUCCESS, result.stdout + result.stderr)
        self.assertIn('AssertionError', result.stderr)
        self.assertIn(producer, result.stderr)

    def test_nested_numeric_types_cannot_agree_by_coercion(self):
        def mutate(row):
            row['original']['typed_control'] = {'amounts': [1, 0]}
            row['candidate']['typed_control'] = {'amounts': [True, 0.0]}
        self.assert_mutation_refused(mutate)

    def test_match_claim_must_be_the_boolean_true(self):
        self.assert_mutation_refused(lambda row: row.__setitem__('match', 1),
                                     'pump_earned_cashback_differential')

    def test_falsey_difference_claim_must_be_an_empty_list(self):
        for claim in (None, {}, False, 0):
            with self.subTest(claim=claim):
                self.assert_mutation_refused(lambda row: row.__setitem__('diff', claim))

    def test_comparison_claim_cannot_be_omitted(self):
        self.assert_mutation_refused(lambda row: row.pop('diff'))

    def test_pristine_packet_still_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            packet = Path(temporary) / 'pump-plain-receipts'
            shutil.copytree(PACKET, packet)
            result = run(packet)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(SUCCESS, result.stdout)


if __name__ == '__main__':
    unittest.main()
