#!/usr/bin/env python3
"""Produce deterministic paired receipts for persistent Mayhem lifecycles."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from lifecycle import HERE, ROOT, lifecycle_plan, run_image, sha256_bytes

ORIGINAL = ROOT / "evidence/original/mayhem/deployed.so"
ORIGINAL_SHA256 = "a87fa9f866272514e6acb852b668c4a08aeb173d56c883039991d114d1199bdb"
CANDIDATE_SHA256 = "9af9e3b1cbc9d89340af4d9d46e4c88d3dc2fc67e0090f9370047d97532ff09d"


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_line(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"


def bound_inputs() -> list[Path]:
    paths = [
        HERE / "fixture.json",
        HERE / "provenance.json",
        HERE / "lifecycle.py",
        HERE / "producer.py",
        HERE / "verify.py",
        ROOT / "scripts/pump_trade_fixture.py",
        ROOT / "research/imported-lab/analysis/pump_fun/curve-fresh-trades-v3-signed-surfpool.json",
        ROOT / "reconstruction/mayhem/native-linux-qualification/QUALIFICATION.json",
        ORIGINAL,
    ]
    for group, names in (
        ("original", ("pump", "pump_fees")),
        ("dependencies", ("spl_token", "spl_token_2022", "associated_token")),
    ):
        for name in names:
            paths.extend(
                (
                    ROOT / f"evidence/{group}/{name}/capture.json",
                    ROOT / f"evidence/{group}/{name}/deployed.so",
                )
            )
    return paths


def produce(candidate: Path, output: Path, original_control: bool = False) -> dict:
    candidate = candidate.resolve()
    if not candidate.is_file():
        raise ValueError(f"candidate is not a regular file: {candidate}")
    if sha256_file(ORIGINAL) != ORIGINAL_SHA256:
        raise ValueError("captured Mayhem original hash mismatch")
    expected = ORIGINAL_SHA256 if original_control else CANDIDATE_SHA256
    if sha256_file(candidate) != expected:
        raise ValueError(f"candidate hash is not the qualified {'control' if original_control else 'rebuild'}")
    output.mkdir(parents=True, exist_ok=False)

    original_rows = run_image(ORIGINAL)
    candidate_rows = run_image(candidate)
    if len(original_rows) != len(candidate_rows):
        raise AssertionError("paired execution count differs")
    rows = []
    for original, rebuilt in zip(original_rows, candidate_rows, strict=True):
        case_id = f"{original['lifecycle']}/{original['step']}"
        if case_id != f"{rebuilt['lifecycle']}/{rebuilt['step']}":
            raise AssertionError("paired execution order differs")
        rows.append({"case_id": case_id, "original": original, "candidate": rebuilt})

    receipt_path = output / "receipts.jsonl"
    receipt_path.write_text("".join(canonical_line(row) for row in rows), encoding="utf-8", newline="\n")
    inputs = {str(path.relative_to(ROOT)): sha256_file(path) for path in bound_inputs()}
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    report = {
        "schema": "mayhem-stateful-lifecycle-report-v1",
        "scope": "Persistent signed Mayhem execution on independent LiteSVM instances; synthetic preinitialized canonical PDAs, captured dependency CPIs, no initialization claim.",
        "source_commit": commit,
        "mode": "original_vs_original" if original_control else "original_vs_candidate",
        "original": {"path": str(ORIGINAL.relative_to(ROOT)), "sha256": ORIGINAL_SHA256, "bytes": ORIGINAL.stat().st_size},
        "candidate": {"path": str(candidate), "sha256": sha256_file(candidate), "bytes": candidate.stat().st_size},
        "input_sha256": inputs,
        "fixture_classification": "synthetic_preinitialized",
        "plan": lifecycle_plan(),
        "receipt_file": receipt_path.name,
        "receipt_sha256": sha256_file(receipt_path),
        "observed_case_count": len(rows),
        "observed_signed_transactions": len(rows) * 2,
    }
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--original-control", action="store_true")
    args = parser.parse_args()
    report = produce(args.candidate, args.output, args.original_control)
    print(json.dumps({key: report[key] for key in ("mode", "observed_case_count", "observed_signed_transactions", "receipt_sha256")}, sort_keys=True))


if __name__ == "__main__":
    main()
