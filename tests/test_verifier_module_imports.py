"""Packet verifiers must import every stdlib module they reference.

A verifier that calls `hashlib.sha256` without importing `hashlib` stops with
NameError before it hashes or replays anything, so every packet it guards is
reported by the crash rather than by an admission check: the run is red for a
reason the packet does not own, and a green run of the same code elsewhere
proves nothing about the packet.  Import-time admission added to many packet
verifiers at once is exactly the kind of edit that leaves one behind, so this
test reads every verifier rather than running them.
"""
import ast
import builtins
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TREES = ('research', 'reconstruction')
BUILTIN_NAMES = set(dir(builtins))


def verifiers():
    """Every packet verifier; `tmpl/` copies carry unrendered placeholders."""
    for tree in TREES:
        for path in sorted((ROOT / tree).rglob('verify.py')):
            if '.git' in path.parts or 'tmpl' in path.parts:
                continue
            yield path


def bound_names(tree):
    """Every name the module binds anywhere: imports, assignments, definitions."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update((alias.asname or alias.name).split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names if alias.name != '*')
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
    return names


def unimported_modules(tree):
    """Stdlib modules used as `module.attribute` that the module never binds."""
    referenced = {node.value.id for node in ast.walk(tree)
                  if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)}
    return sorted(referenced & set(sys.stdlib_module_names) - bound_names(tree) - BUILTIN_NAMES)


class VerifierModuleImportTests(unittest.TestCase):
    def test_every_referenced_stdlib_module_is_imported(self):
        paths = list(verifiers())
        self.assertGreater(len(paths), 150, 'verifier discovery found too few packets')
        missing = {}
        for path in paths:
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            modules = unimported_modules(tree)
            if modules:
                missing[str(path.relative_to(ROOT))] = modules
        self.assertEqual({}, missing)


if __name__ == '__main__':
    unittest.main()
