#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

from lifecycle import run_image  # noqa: E402
from producer import ORIGINAL, canonical_line, produce, sha256_file  # noqa: E402
from verify import verify  # noqa: E402


class StatefulLifecycleTests(unittest.TestCase):
    def test_captured_original_has_real_success_failure_and_persistence(self):
        rows = run_image(ORIGINAL)
        self.assertEqual(len(rows), 10)
        self.assertEqual(sum(row["error"] is None for row in rows), 7)
        self.assertEqual(sum(row["error"] is not None for row in rows), 3)
        self.assertEqual(rows[0]["after"], rows[1]["before"])
        self.assertEqual(rows[1]["after"], rows[2]["before"])
        self.assertIn("InstructionErrorCustom(6000)", rows[4]["error"])
        self.assertIn("InstructionErrorCustom(2001)", rows[5]["error"])
        self.assertEqual(rows[8]["before"], rows[7]["after"])

    def test_original_control_verifies_and_replays_byte_identically(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            produce(ORIGINAL, first, original_control=True)
            produce(ORIGINAL, second, original_control=True)
            self.assertEqual((first / "receipts.jsonl").read_bytes(), (second / "receipts.jsonl").read_bytes())
            self.assertEqual((first / "report.json").read_bytes(), (second / "report.json").read_bytes())
            result = verify(first / "report.json", ORIGINAL)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["equal_observed_behavior"], 10)
            self.assertTrue(all(row["detected"] for row in result["negative_controls"]))

    def test_semantic_tamper_fails_after_receipt_hash_is_resealed(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "control"
            produce(ORIGINAL, output, original_control=True)
            report_path = output / "report.json"
            report = json.loads(report_path.read_text())
            receipt_path = output / report["receipt_file"]
            rows = [json.loads(line) for line in receipt_path.read_text().splitlines()]
            changed = copy.deepcopy(rows)
            receipt = changed[0]["candidate"]
            key = receipt["account_roles"]["fee_recipient"]
            receipt["after"][key]["lamports"] += 1
            receipt_path.write_text("".join(canonical_line(row) for row in changed), encoding="utf-8", newline="\n")
            report["receipt_sha256"] = sha256_file(receipt_path)
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(ValueError, "SOL conservation"):
                verify(report_path, ORIGINAL)

    def test_producer_summary_is_not_an_acceptance_oracle(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "control"
            produce(ORIGINAL, output, original_control=True)
            report_path = output / "report.json"
            report = json.loads(report_path.read_text())
            report["observed_case_count"] = 999999
            report["observed_signed_transactions"] = 0
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
            result = verify(report_path, ORIGINAL)
            self.assertEqual(result["case_count"], 10)
            self.assertEqual(result["signed_transaction_count"], 20)
            self.assertFalse(result["producer_summary_fields_trusted"])

    def test_unqualified_candidate_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.so"
            candidate.write_bytes(b"not a qualified Mayhem image")
            with self.assertRaisesRegex(ValueError, "candidate hash"):
                produce(candidate, root / "output")


if __name__ == "__main__":
    unittest.main()
