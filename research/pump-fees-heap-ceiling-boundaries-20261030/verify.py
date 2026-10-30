#!/usr/bin/env python3
"""Replay every family on both images and compare with the packet's runtime files.

usage (inside the packet folder): python3 verify.py --images '{"original": p, "candidate": p}'
Exit 0 = receipts and report reproduced byte for byte and every recorded claim holds.
"""
import sys
sys.dont_write_bytecode = True
import argparse, gzip, hashlib, json, pathlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import producer


def fail(msg):
    print('FAIL:', msg)
    sys.exit(1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--images', required=True)
    a = p.parse_args()
    images = producer.load_images(a.images)
    rt = HERE / 'runtime'
    report = json.loads(gzip.decompress((rt / 'report.json.gz').read_bytes()))
    for n, path in images.items():
        if hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() != report['image_sha256'][n]:
            fail(f'{n} image sha256 differs from the report')
    rec, rep = producer.encode(*producer.produce(images, producer.families()))
    if rec != (rt / 'receipts.jsonl.gz').read_bytes():
        fail('receipts differ from the replay')
    if rep != (rt / 'report.json.gz').read_bytes():
        fail('report differs from the replay')
    if report['edge_mismatched_families'] or report['grid_class_mismatched_families']:
        fail('outcome edges differ between the images')
    for f in report['families']:
        if f['edges_original'] != f['edges_candidate']:
            fail(f['name'])
        # the only allowed difference is the empty-list panic: +16 CU and a longer source path, x = 0
        for d in f['grid_cu_diffs']:
            if d['x'] != 0 or d['candidate'] - d['original'] != 16:
                fail(f"{f['name']} unexpected CU difference {d}")
        if any(x != 0 for x in f['grid_log_diffs']):
            fail(f"{f['name']} unexpected log difference")
    frames = {f['heap_frame']: f for f in report['families'] if f['name'].startswith('declared-string-frame-')}
    if len({f['edges_original'][0][0] for f in frames.values()}) != 1:
        fail('a heap frame moved the declared-string boundary')
    print(json.dumps({'families': report['family_count'], 'edges': sum(len(f['edges_original']) for f in report['families']), 'result': 'pass'}))


if __name__ == '__main__':
    main()
