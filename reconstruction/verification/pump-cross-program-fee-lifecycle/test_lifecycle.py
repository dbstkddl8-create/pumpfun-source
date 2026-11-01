#!/usr/bin/env python3
"""Regression and admission tests for the cross-program lifecycle packet."""
from __future__ import annotations

import base64
import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lifecycle as life  # noqa: E402
import verify as reader  # noqa: E402


class CrossProgramLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.control = life.run_suite(life.base.CAPTURED["pump_original"])
        cls.control["negative_controls"] = life.negative_controls(cls.control)

    def test_original_control_is_supported_and_equal(self):
        self.assertEqual(self.control["classification"], "equal_observed_behavior")
        self.assertEqual(self.control["mismatch_fields"], [])
        self.assertEqual(self.control["receipt_failures"], {"original": [], "candidate": []})
        self.assertEqual(self.control["invariant_failures"], {"original": [], "candidate": []})
        self.assertEqual(self.control["infrastructure_failures"], [])
        self.assertEqual(reader.verify(self.control, life.base.CAPTURED["pump_original"]), [])

    def test_plan_has_persistent_and_atomic_transitions(self):
        self.assertEqual(len(life.STEPS), 11)
        self.assertEqual(sum(len(step["operations"]) > 1 for step in life.STEPS), 2)
        names = [step["name"] for step in life.STEPS]
        self.assertLess(names.index("trade-A"), names.index("collect-A"))
        self.assertLess(names.index("admin-A-to-B"), names.index("trade-B"))
        self.assertLess(names.index("atomic-unswept-B-to-C"), names.index("atomic-sweep-B-to-C-retry"))
        self.assertLess(names.index("atomic-sweep-B-to-C-retry"), names.index("trade-C"))

    def test_transactions_are_genuinely_signed_and_program_routed(self):
        program_for = {
            "amm_buy_v2": life.AMM,
            "amm_sweep_creator_fee": life.AMM,
            "amm_collect_creator_fee": life.AMM,
            "pump_admin_cto": life.PUMP,
            "pump_collect_creator_fee": life.PUMP,
        }
        for side in ("original", "candidate"):
            signatures = []
            for row, plan in zip(self.control[side]["receipts"], life.STEPS):
                tx = life.Transaction.from_bytes(base64.b64decode(row["transaction_base64"], validate=True))
                self.assertEqual(list(tx.verify_with_results()), [True] * tx.message.header.num_required_signatures)
                self.assertEqual(len(tx.message.instructions), 1 + len(plan["operations"]))
                routed = [tx.message.account_keys[ix.program_id_index] for ix in tx.message.instructions[1:]]
                self.assertEqual(routed, [program_for[operation["op"]] for operation in plan["operations"]])
                signers = set(tx.message.account_keys[:tx.message.header.num_required_signatures])
                self.assertTrue(signers <= {life.PAYER.pubkey(), life.ADMIN.pubkey()})
                self.assertNotIn(life.Harness._mint_fixture(0, "native").pool_authority, signers)
                signatures.append(str(tx.signatures[0]))
            self.assertEqual(len(signatures), len(set(signatures)))

    def test_fixture_addresses_are_canonical(self):
        harness = life.Harness(life.base.CAPTURED["pump_original"])
        fixture = harness.fixture
        self.assertEqual(fixture.curve, life.base.pda(b"bonding-curve", bytes(fixture.mint)))
        self.assertEqual(fixture.pool_authority, life.base.pda(b"pool-authority", bytes(fixture.mint)))
        expected_pool = life.base.pda(
            b"pool", bytes(2), bytes(fixture.pool_authority), bytes(fixture.mint), bytes(fixture.quote),
            program=life.AMM,
        )
        self.assertEqual(fixture.pool, expected_pool)
        self.assertEqual(harness.pool_base, life.base.ata(fixture.pool, fixture.mint, life.TOKEN))
        self.assertEqual(harness.pool_quote, life.base.ata(fixture.pool, fixture.quote, life.TOKEN))

    def test_failure_rolls_back_trade_before_failing_admin(self):
        for side in ("original", "candidate"):
            row = next(item for item in self.control[side]["receipts"]
                       if item["step"] == "atomic-unswept-B-to-C")
            self.assertIn("CreatorFeesNotSwept", row["outcome"])
            self.assertTrue(row["rollback_nonfee_equal"])
            self.assertEqual(
                {k: v for k, v in row["before"].items() if k != str(life.PAYER.pubkey())},
                {k: v for k, v in row["after"].items() if k != str(life.PAYER.pubkey())},
            )

    def test_negative_controls_hit_strict_comparator(self):
        self.assertEqual(self.control["negative_controls"], {
            "error": True, "after": True, "events": True, "inner_instructions": True,
        })

    def test_reader_rejects_tampered_receipts_and_cached_summaries(self):
        mutations = {}

        changed = copy.deepcopy(self.control)
        changed["candidate"]["receipts"][0]["error"] = "forged"
        mutations["error"] = changed

        changed = copy.deepcopy(self.control)
        changed["candidate"]["receipts"][0]["after"]["forged"] = None
        mutations["state"] = changed

        changed = copy.deepcopy(self.control)
        row = changed["candidate"]["receipts"][0]
        raw = bytearray(base64.b64decode(row["transaction_base64"], validate=True))
        raw[0] ^= 1
        row["transaction_base64"] = base64.b64encode(raw).decode()
        mutations["signature"] = changed

        changed = copy.deepcopy(self.control)
        changed["classification"] = "equal_observed_behavior"
        changed["mismatch_fields"] = ["forged"]
        mutations["summary"] = changed

        changed = copy.deepcopy(self.control)
        changed["candidate_provenance"]["candidate_sha256"] = "0" * 64
        mutations["provenance"] = changed

        for name, report in mutations.items():
            with self.subTest(name=name):
                self.assertTrue(reader.verify(report, life.base.CAPTURED["pump_original"]))

    def test_canonical_report_bytes_are_deterministic_and_exclusive(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first.json.gz"
            second = Path(temporary) / "second.json.gz"
            life.write_report(first, self.control)
            life.write_report(second, self.control)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with self.assertRaises(FileExistsError):
                life.write_report(first, self.control)


if __name__ == "__main__":
    unittest.main()
