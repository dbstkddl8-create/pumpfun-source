#!/usr/bin/env python3
"""Independently verify or replay a cross-program fee lifecycle report."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import lifecycle


def read_report(path: Path) -> dict:
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def expected_program_hashes(candidate: Path) -> dict:
    rows = {name: lifecycle.base.file_sha(path) for name, path in lifecycle.base.CAPTURED.items()}
    rows["pump_candidate"] = lifecycle.base.file_sha(candidate)
    return rows


def expected_classification(mismatches, receipt_failures, invariant_failures, infrastructure) -> str:
    if infrastructure:
        return "infrastructure_failure"
    if invariant_failures["original"] or receipt_failures["original"]:
        return "unsupported_fixture"
    if mismatches or invariant_failures["candidate"] or receipt_failures["candidate"]:
        return "different_behavior"
    return "equal_observed_behavior"


def verify(report: dict, candidate: Path) -> list[str]:
    problems = []
    if report.get("schema") != "pump-cross-program-fee-lifecycle-v1":
        problems.append("schema")
    expected_ids = {
        "pump": str(lifecycle.PUMP), "pump_amm": str(lifecycle.AMM),
        "pump_fees": str(lifecycle.FEES), "spl_token": str(lifecycle.TOKEN),
        "associated_token": str(lifecycle.ATA),
    }
    if report.get("program_ids") != expected_ids:
        problems.append("program_ids")
    if report.get("program_sha256") != expected_program_hashes(candidate):
        problems.append("program_sha256")
    if report.get("idl_sha256") != {
        "pump": lifecycle.base.sha(lifecycle.base.IDL_BYTES),
        "pump_amm": lifecycle.base.sha(lifecycle.AMM_IDL_BYTES),
    }:
        problems.append("idl_sha256")
    if report.get("fixture_sha256") != lifecycle.base.sha(lifecycle.TRADE_FIXTURE_BYTES):
        problems.append("fixture_sha256")
    expected_inputs = {
        path.relative_to(lifecycle.ROOT).as_posix(): lifecycle.base.file_sha(path)
        for path in lifecycle.PRODUCER_PATHS
    }
    if report.get("producer_input_sha256") != expected_inputs:
        problems.append("producer_input_sha256")
    sources, source_digest = lifecycle.source_manifest()
    if (report.get("source_files") != sources
            or report.get("source_manifest_sha256") != source_digest):
        problems.append("source_manifest")

    original = report.get("original")
    candidate_run = report.get("candidate")
    if not isinstance(original, dict) or not isinstance(candidate_run, dict):
        return problems + ["runs"]
    planned_names = [step["name"] for step in lifecycle.STEPS]
    expected_operations = {
        step["name"]: "+".join(operation["op"] for operation in step["operations"])
        for step in lifecycle.STEPS
    }
    all_signatures = {"original": [], "candidate": []}
    for side, run in (("original", original), ("candidate", candidate_run)):
        receipts = run.get("receipts", [])
        if [row.get("step") for row in receipts] != planned_names:
            problems.append(side + ":step_membership")
        for row, plan in zip(receipts, lifecycle.STEPS):
            if (row.get("operations") != plan["operations"]
                    or row.get("operation") != expected_operations[plan["name"]]):
                problems.append(side + ":" + plan["name"] + ":operation_plan")
            all_signatures[side].append(row.get("signature"))
        if len(all_signatures[side]) != len(set(all_signatures[side])):
            problems.append(side + ":duplicate_signature")

    mismatches, comparison = lifecycle.compare_runs(original, candidate_run)
    if (report.get("mismatch_fields") != mismatches
            or report.get("comparison") != comparison):
        problems.append("comparison")
    receipt_failures = {
        "original": lifecycle.validate_run(original),
        "candidate": lifecycle.validate_run(candidate_run),
    }
    if report.get("receipt_failures") != receipt_failures:
        problems.append("receipt_failures")
    invariant_failures = {
        "original": lifecycle.lifecycle_invariants(original),
        "candidate": lifecycle.lifecycle_invariants(candidate_run),
    }
    if report.get("invariant_failures") != invariant_failures:
        problems.append("invariant_failures")
    infrastructure = [
        f"{side}:{row['step']}"
        for side, run in (("original", original), ("candidate", candidate_run))
        for row in run["receipts"] if lifecycle.base.failure_class(row.get("error")) == "infrastructure"
    ]
    if report.get("infrastructure_failures") != infrastructure:
        problems.append("infrastructure_failures")
    classification = expected_classification(
        mismatches, receipt_failures, invariant_failures, infrastructure
    )
    if report.get("classification") != classification:
        problems.append("classification")
    if report.get("transaction_count_per_image") != len(lifecycle.STEPS):
        problems.append("transaction_count_per_image")
    multi = sum(len(step["operations"]) > 1 for step in lifecycle.STEPS)
    if report.get("multi_instruction_transactions_per_image") != multi:
        problems.append("multi_instruction_transactions_per_image")
    controls = lifecycle.negative_controls(report)
    expected_controls = {"error": True, "after": True, "events": True, "inner_instructions": True}
    if controls != expected_controls or report.get("negative_controls") != controls:
        problems.append("negative_controls")
    if classification != "equal_observed_behavior":
        problems.append("qualification_failure:" + classification)
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    report = read_report(args.report)
    problems = verify(report, args.candidate.resolve())
    replay_equal = None
    if args.replay and not problems:
        replay = lifecycle.run_suite(args.candidate.resolve())
        replay["negative_controls"] = lifecycle.negative_controls(replay)
        replay_equal = replay == report
        if not replay_equal:
            problems.append("deterministic_replay")
    print(json.dumps({
        "verified": not problems,
        "problems": problems,
        "deterministic_replay_equal": replay_equal,
    }, indent=2))
    return bool(problems)


if __name__ == "__main__":
    raise SystemExit(main())
