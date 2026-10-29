import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseExpression } from '@babel/parser';
import { normalizeUserSearch } from '../scripts/verify-user-search.mjs';

test('inherited Object.prototype names are not treated as supplied user-search roles', () => {
  for (const name of ['toString', 'constructor', 'hasOwnProperty', 'valueOf']) {
    assert.throws(() => normalizeUserSearch(parseExpression(`(query) => ${name}(query)`), {}),
      new RegExp(`unresolved user-search bindings: ${name}`));
  }
});

test('distinct unbound inherited names cannot normalize to the same workflow', () => {
  const roles = { request: 'request' };
  assert.throws(() => normalizeUserSearch(parseExpression('(query) => request(toString(query))'), roles),
    /unresolved user-search bindings: toString/);
  assert.throws(() => normalizeUserSearch(parseExpression('(query) => request(valueOf(query))'), roles),
    /unresolved user-search bindings: valueOf/);
});

test('own role names still resolve', () => {
  const normalized = normalizeUserSearch(parseExpression('(query) => toString(query)'), { toString: 'request' });
  assert.equal(normalized.body.callee.name, 'request');
});
