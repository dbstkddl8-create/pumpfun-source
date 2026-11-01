"""The borrowed-selection packet pins every file it ships.

The verifier hashed the files its MANIFEST.json named but never compared that
list with the folder it lives in. `VALIDATION.json`, the 140 KB retained
capture archive and `verification.json` — the packet's own PASS record — sat
beside the pinned files with no entry, so a reader could not tell whether they
had been altered, and a pin could be dropped by editing the manifest alone.
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "reconstruction/pump-main/lanes/borrowed-selection-s5-negative-20261031"


class BorrowedSelectionPacketFilesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.packet = Path(self.temporary.name) / PACKET.name
        shutil.copytree(PACKET, self.packet)

    def tearDown(self):
        self.temporary.cleanup()

    def listed(self):
        return json.loads((PACKET / "MANIFEST.json").read_bytes())["files"]

    def run_packet(self):
        return subprocess.run(
            [sys.executable, "-B", str(self.packet / "verify.py")],
            capture_output=True,
            text=True,
        )

    def test_manifest_names_every_shipped_file(self):
        shipped = {path.name for path in PACKET.iterdir()
                   if path.is_file() and path.name != "MANIFEST.json"}
        self.assertEqual(set(self.listed()), shipped)

    def test_pinned_hashes_match_the_shipped_bytes(self):
        for name, row in self.listed().items():
            with self.subTest(name=name):
                data = (PACKET / name).read_bytes()
                self.assertEqual(len(data), row["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), row["sha256"])

    def test_intact_packet_reaches_its_arguments(self):
        # Admission runs before argparse, so an intact copy still reports the
        # missing required options rather than a packet error.
        completed = self.run_packet()
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("usage", completed.stderr.lower())

    def test_an_altered_pinned_file_is_refused_before_arguments(self):
        path = self.packet / "verification.json"
        path.write_bytes(path.read_bytes() + b" ")
        completed = self.run_packet()
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("verification.json", completed.stderr)
        self.assertNotIn("usage", completed.stderr.lower())

    def test_an_unlisted_file_is_refused(self):
        (self.packet / "unlisted.json").write_text("{}\n", encoding="utf-8")
        completed = self.run_packet()
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("MANIFEST.json", completed.stderr)

    def test_a_deleted_file_is_refused(self):
        (self.packet / "inputs.json").unlink()
        completed = self.run_packet()
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("MANIFEST.json", completed.stderr)


if __name__ == "__main__":
    unittest.main()
