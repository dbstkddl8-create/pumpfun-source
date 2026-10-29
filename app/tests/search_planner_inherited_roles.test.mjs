import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseExpression } from '@babel/parser';
import { normalizePlanner } from '../scripts/verify-search-planner.mjs';

test('inherited Object.prototype names are not treated as supplied planner roles', () => {
  for (const name of ['toString', 'constructor', 'hasOwnProperty', 'valueOf']) {
    assert.throws(() => normalizePlanner(parseExpression(`(key) => ${name}(key)`), {}),
      new RegExp(`unresolved planner bindings: ${name}`));
  }
});

test('distinct unbound inherited names cannot normalize to the same matcher', () => {
  const roles = { normalize: 'normalize:key' };
  const left = () => JSON.stringify(normalizePlanner(parseExpression('(key) => normalize(toString(key))'), roles));
  const right = () => JSON.stringify(normalizePlanner(parseExpression('(key) => normalize(valueOf(key))'), roles));
  assert.throws(left, /unresolved planner bindings: toString/);
  assert.throws(right, /unresolved planner bindings: valueOf/);
});

test('own role names still resolve', () => {
  const normalized = normalizePlanner(parseExpression('(key) => toString(key)'), { toString: 'normalize:key' });
  assert.equal(normalized.body.callee.name, 'normalize:key');
});
