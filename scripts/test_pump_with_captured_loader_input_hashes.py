#!/usr/bin/env python3
"""A captured-loader receipt binds the inputs the run started from."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
WRAPPER = HERE / "pump_with_captured_loader.py"
HARNESS = "from pathlib import Path\nPath(__file__).write_text('# replaced\\n')\n"
LOADER = (
    "from pathlib import Path\n"
    "ROOT = Path(__file__).resolve().parents[1]\n"
    "LOADS = []\n"
    "def install():\n"
    "    pass\n"
)


class CapturedLoaderInputHashTests(unittest.TestCase):
    def test_receipt_keeps_the_hash_of_the_harness_that_ran(self):
        with tempfile.TemporaryDirectory(prefix="captured-loader-hashes-") as temporary:
            root = Path(temporary).resolve()
            scripts = root / "scripts"
            scripts.mkdir()
            wrapper = scripts / WRAPPER.name
            shutil.copyfile(WRAPPER, wrapper)
            (scripts / "pump_captured_loader.py").write_text(LOADER, encoding="utf-8")
            evidence = root / "evidence/original/pump"
            evidence.mkdir(parents=True)
            for name in ("capture.json", "program-account.bin",
                         "programdata-account.bin", "deployed.so"):
                (evidence / name).write_bytes(name.encode())
            harness = root / "harness.py"
            harness.write_text(HARNESS, encoding="utf-8")
            expected = hashlib.sha256(HARNESS.encode()).hexdigest()
            receipt = root / "receipt.json"

            result = subprocess.run(
                [sys.executable, "-B", str(wrapper), "--receipt", str(receipt), str(harness)],
                text=True, capture_output=True)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(harness.read_text(encoding="utf-8"), "# replaced\n")
            record = json.loads(receipt.read_text())
            self.assertEqual(record["input_sha256"][str(harness)], expected)


if __name__ == "__main__":
    unittest.main()
