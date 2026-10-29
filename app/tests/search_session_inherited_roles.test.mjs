import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseExpression } from '@babel/parser';
import { normalizeSession } from '../scripts/verify-search-session.mjs';

test('inherited Object.prototype names are not treated as supplied session roles', () => {
  for (const name of ['toString', 'constructor', 'hasOwnProperty', 'valueOf']) {
    assert.throws(() => normalizeSession(parseExpression(`(query) => ${name}(query)`), {}),
      new RegExp(`unresolved session bindings: ${name}`));
  }
});

test('distinct unbound inherited names cannot normalize to the same session workflow', () => {
  const roles = { request: 'request' };
  assert.throws(() => normalizeSession(parseExpression('(query) => request(toString(query))'), roles),
    /unresolved session bindings: toString/);
  assert.throws(() => normalizeSession(parseExpression('(query) => request(valueOf(query))'), roles),
    /unresolved session bindings: valueOf/);
});

test('own session role names still resolve', () => {
  const normalized = normalizeSession(parseExpression('(query) => toString(query)'), { toString: 'request' });
  assert.equal(normalized.body.callee.name, 'request');
});
