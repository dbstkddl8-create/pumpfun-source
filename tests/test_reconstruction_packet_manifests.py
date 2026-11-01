"""Reconstruction packets that pin their own folder must check that pin.

A packet that ships `MANIFEST.json` and never reads it records nothing: a
member can change, or a file can be added, and the verifier still prints its
result.  The packets selected here record exactly the files their folder holds
(their own MANIFEST.json aside), so the verifier can compare the recorded paths
with the folder and each recorded hash with the bytes.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / 'reconstruction'
WALKS = ('rglob(', 'iterdir(', 'os.walk(', 'os.scandir(')


def listed(manifest):
    """Recorded paths, whichever shape the packet uses for its file record."""
    document = json.loads(manifest.read_text(encoding='utf-8'))
    files = document.get('files', document) if isinstance(document, dict) else document
    if isinstance(files, list):
        return {entry['path'] for entry in files}
    return set(files) if isinstance(files, dict) else set()


def pinned_packets():
    """Packets whose MANIFEST.json names exactly the files that folder holds."""
    for verifier in sorted(TREE.rglob('verify.py')):
        manifest = verifier.parent / 'MANIFEST.json'
        if not manifest.is_file():
            continue
        present = {path.relative_to(verifier.parent).as_posix()
                   for path in verifier.parent.rglob('*')
                   if path.is_file() and path != manifest}
        if listed(manifest) and listed(manifest) == present:
            yield verifier


class ReconstructionPacketManifestTests(unittest.TestCase):
    def test_every_pinned_packet_verifier_reads_and_walks_its_folder(self):
        verifiers = list(pinned_packets())
        self.assertGreaterEqual(len(verifiers), 3, 'packet discovery found too few manifests')
        unchecked = []
        for verifier in verifiers:
            text = verifier.read_text(encoding='utf-8')
            if 'MANIFEST.json' not in text or not any(walk in text for walk in WALKS):
                unchecked.append(str(verifier.relative_to(ROOT)))
        self.assertEqual([], unchecked)


if __name__ == '__main__':
    unittest.main()
