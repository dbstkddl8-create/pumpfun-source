#!/usr/bin/env python3
"""Replay every case on both images and compare with the packet's runtime files.

usage (inside the packet folder): python3 verify.py --images '{"original": p, "candidate": p}'
The pump and pump_amm dependencies are found next to the original image
(<original dir>/../pump/deployed.so, <original dir>/../pump_amm/deployed.so).
Exit 0 = receipts and report reproduced byte for byte and no case differs between the images.
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
    base = pathlib.Path(images['original']).resolve().parent.parent
    paths = dict(images, pump=str(base / 'pump/deployed.so'), pump_amm=str(base / 'pump_amm/deployed.so'))
    rt = HERE / 'runtime'
    report = json.loads(gzip.decompress((rt / 'report.json.gz').read_bytes()))
    for k, n in [('original', 'original'), ('candidate', 'candidate'), ('pump', 'pump_dependency'), ('pump_amm', 'pump_amm_dependency')]:
        if hashlib.sha256(pathlib.Path(paths[k]).read_bytes()).hexdigest() != report['images_sha256'][n]:
            fail(f'{k} image sha256 differs from the report')
    rec, rep, _ = producer.build(paths, producer.cases())
    if rec != (rt / 'receipts.jsonl.gz').read_bytes():
        fail('receipts differ from the replay')
    if rep != (rt / 'report.json.gz').read_bytes():
        fail('report differs from the replay')
    if report['behavior_mismatch_cases'] or report['cu_mismatch_cases']:
        fail('a case differs between the images')
    print(json.dumps({'cases': report['case_count'], 'steps': report['step_count'], 'result': 'pass'}))


if __name__ == '__main__':
    main()
