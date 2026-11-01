"""Private packet copies must be admitted before helpers or external inputs run."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'reconstruction/pump-main/checkpoints/native-6a1d23a-20261030'
BORROWED = ROOT / 'reconstruction/pump-main/lanes/borrowed-selection-s5-negative-20261031'


class PacketAdmissionBoundaries(unittest.TestCase):
    def run_packet(self, packet, *arguments):
        return subprocess.run([sys.executable, '-B', str(packet / 'verify.py'), *arguments],
                              capture_output=True, text=True)

    def test_native_helper_is_checked_before_its_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            packet = root / 'packet'
            shutil.copytree(NATIVE, packet)
            marker = root / 'executed'
            helper = packet / 'qualification.py'
            helper.write_text('from pathlib import Path\nPath(' + repr(str(marker)) +
                              ').write_text("executed")\n' + helper.read_text())
            result = self.run_packet(packet, '--original', '/missing/original.so')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())
            self.assertIn('qualification.py', result.stdout + result.stderr)
            self.assertNotIn('/missing/original.so', result.stdout + result.stderr)

    def test_borrowed_rejects_redirected_and_unlisted_nested_members(self):
        for mode in ('symlink', 'nested', 'bytecode', 'duplicate'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                packet = root / 'packet'
                shutil.copytree(BORROWED, packet)
                if mode == 'symlink':
                    (packet / 'verification.json').replace(root / 'outside.json')
                    try:
                        (packet / 'verification.json').symlink_to(root / 'outside.json')
                    except OSError as error:
                        self.skipTest('symlink privilege unavailable: ' + str(error))
                elif mode == 'nested':
                    (packet / 'nested').mkdir()
                    (packet / 'nested/unlisted.bin').write_bytes(b'extra')
                elif mode == 'bytecode':
                    (packet / '__pycache__').mkdir()
                    (packet / '__pycache__/stale.pyc').write_bytes(b'cached')
                else:
                    path = packet / 'MANIFEST.json'
                    path.write_text(path.read_text().replace('"files": {', '"files": {"NOTES.md": {},', 1))
                result = self.run_packet(packet)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('usage:', result.stderr)
                self.assertTrue(any(mark in result.stdout + result.stderr for mark in
                                    ('symlink', 'cached bytecode', 'file set differs', 'duplicate packet')))


    def test_reconstruction_packets_admit_before_external_inputs(self):
        cases = [
            (NATIVE, ['--original', '/missing/original.so']),
            (ROOT / 'reconstruction/pump-main/lanes/cto-creator-fee-s1-s2-negative-20261031',
             ['--repo', '/missing/repository']),
            (ROOT / 'reconstruction/pump-main/lanes/cto-option-c1-negative-20261031',
             ['--repo', '/missing/repository']),
            (ROOT / 'reconstruction/pump-main/lanes/hopt-h1-negative-20261031',
             ['--repo', '/missing/repository', '--native-zip', '/missing/native.zip',
              '--control-zip', '/missing/control.zip', '--capsule', '/missing/capsule']),
            (ROOT / 'reconstruction/pump-main/lanes/original-creator-consumers-20261031',
             ['--repo', '/missing/repository']),
        ]
        for source, arguments in cases:
            for mode in ('changed', 'extra', 'symlink', 'bytecode'):
                with self.subTest(packet=source.name, mode=mode), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    packet = root / 'packet'
                    shutil.copytree(source, packet)
                    manifest = json.loads((packet / 'MANIFEST.json').read_bytes())['files']
                    names = [row['path'] for row in manifest] if isinstance(manifest, list) else list(manifest)
                    name = next(name for name in names if name != 'verify.py' and name.endswith(('.md', '.json')))
                    if mode == 'changed':
                        member = packet / name
                        member.write_bytes(member.read_bytes() + b'changed')
                    elif mode == 'extra':
                        (packet / 'unlisted.bin').write_bytes(b'extra')
                    elif mode == 'symlink':
                        (packet / name).replace(root / 'outside')
                        try:
                            (packet / name).symlink_to(root / 'outside')
                        except OSError as error:
                            self.skipTest('symlink privilege unavailable: ' + str(error))
                    else:
                        (packet / '__pycache__').mkdir()
                        (packet / '__pycache__/stale.pyc').write_bytes(b'cached')
                    result = self.run_packet(packet, *arguments)
                    output = result.stdout + result.stderr
                    self.assertNotEqual(result.returncode, 0, output)
                    self.assertNotIn('/missing/', output)
                    self.assertTrue(any(mark in output for mark in
                                        ('MANIFEST.json', 'symlink', 'cached bytecode')), output)


if __name__ == '__main__':
    unittest.main()
