#!/usr/bin/env python3
"""Replay every length probe of this packet on both images and compare with the stored receipts.

The probes rewrite one immediate in an in-memory copy of each image; nothing is written to disk.

Usage (from the packet folder): python3 verify.py --images '{"original": "...", "candidate": "..."}'
Optional --root <repo> also re-reads the merged packets' receipts behind runtime/merged-sites.json.gz.
Exit 0 = everything reproduced, 1 = a difference was found.
"""
import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import producer  # noqa: E402


def load_gz(name):
    return gzip.decompress((HERE / 'runtime' / name).read_bytes()).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--images', required=True)
    ap.add_argument('--root', type=Path)
    args = ap.parse_args()
    images = json.loads(args.images)
    errors = []
    manifest = json.loads((HERE / 'MANIFEST.json').read_text())
    listed = set()
    for f in manifest['files']:
        p = HERE / f['path']
        listed.add(f['path'])
        if not p.exists():
            errors.append(f"missing {f['path']}")
            continue
        b = p.read_bytes()
        if hashlib.sha256(b).hexdigest() != f['sha256'] or len(b) != f['bytes']:
            errors.append(f"manifest mismatch {f['path']}")
    actual = {str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file()} - {'MANIFEST.json'}
    actual = {a for a in actual if '__pycache__' not in a}
    if actual != listed:
        errors.append(f'manifest file set differs: {sorted(actual ^ listed)}')
    report = json.loads(load_gz('report.json.gz'))
    blobs = {n: Path(images[n]).read_bytes() for n in ('original', 'candidate')}
    for n, b in blobs.items():
        if hashlib.sha256(b).hexdigest() != report['images'][n]:
            errors.append(f'image {n}: sha256 differs from the report')
    if errors:
        print('\n'.join(errors))
        return 1
    plan = json.loads(load_gz('plan.json.gz'))
    if plan['probes'] != producer.probe_plan():
        errors.append('plan differs from producer.probe_plan()')
    res = producer.run_probes(blobs)
    if producer.receipts_text(plan['probes'], res) != load_gz('receipts.jsonl.gz'):
        errors.append('receipts: replay differs from the stored receipts')
    mined = json.loads(load_gz('merged-sites.json.gz'))
    if args.root and producer.mine(args.root) != mined:
        errors.append('merged-sites differs from the repository receipts')
    a = producer.analyse(plan['probes'], res, mined)
    if json.dumps(a, sort_keys=True) != json.dumps(report['analysis'], sort_keys=True):
        errors.append('analysis differs from the report')
    if a['l145_equal_length_equal_cu'] != a['l145_probes'] or a['l123_equal_length_equal_cu'] != a['l123_probes']:
        errors.append('a probe has different CU or length on the two images')
    if errors:
        print('\n'.join(errors))
        return 1
    print(f"OK: {len(plan['probes'])} probes reproduced on both images")
    return 0


if __name__ == '__main__':
    sys.exit(main())
