"""The recovered error table speaks the text the IDL declares.

`tests/test_error_sites_captured.py` compared a printed message with
``expected[code].get('msg', message)``: for the 18 IDL codes that declare no
``msg``, the value under test supplied its own expectation, so any text
passed. Solana reports the error's name when no message is declared, and this
pins that rule to the table the host prints from, without a VM.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDL = json.loads((ROOT / "evidence/upstream/pump.json").read_text(encoding="utf-8"))
SOURCE = (ROOT / "programs/pump/recovered/error_sites.rs").read_text(encoding="utf-8")
ROW = re.compile(r'^\s*\((\d+), "([^"]*)", "([^"]*)"\),\s*$', re.M)


class ErrorMessageTableTests(unittest.TestCase):
    def rows(self):
        rows = [(int(code), name, message) for code, name, message in ROW.findall(SOURCE)]
        # A parse that matched nothing would make every check below vacuous.
        self.assertGreater(len(rows), 50, "recovered error table not parsed")
        return rows

    def test_custom_messages_match_the_idl(self):
        errors = {entry["code"]: entry for entry in IDL["errors"]}
        checked = 0
        for code, name, message in self.rows():
            if not 6000 <= code < 7000:
                continue
            with self.subTest(code=code):
                self.assertIn(code, errors)
                self.assertEqual(name, errors[code]["name"])
                # Solana reports the error's name when no #[msg] is declared.
                self.assertEqual(message, errors[code].get("msg", errors[code]["name"]))
            checked += 1
        self.assertGreater(checked, 50, "no custom error rows were compared")


if __name__ == "__main__":
    unittest.main()
