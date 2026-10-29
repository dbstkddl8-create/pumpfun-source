import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseExpression } from '@babel/parser';
import { normalizeNavigation } from '../scripts/verify-search-navigation.mjs';

test('inherited Object.prototype names are not treated as supplied navigation roles', () => {
  for (const name of ['toString', 'constructor', 'hasOwnProperty', 'valueOf']) {
    assert.throws(() => normalizeNavigation(parseExpression(`(value) => ${name}(value)`), {}),
      new RegExp(`unresolved navigation bindings: ${name}`));
  }
});

test('distinct unbound inherited names cannot normalize to the same navigation', () => {
  const roles = { route: 'operation:route' };
  assert.throws(() => normalizeNavigation(parseExpression('(value) => route(toString(value))'), roles),
    /unresolved navigation bindings: toString/);
  assert.throws(() => normalizeNavigation(parseExpression('(value) => route(valueOf(value))'), roles),
    /unresolved navigation bindings: valueOf/);
});

test('own role names still resolve', () => {
  const normalized = normalizeNavigation(parseExpression('(value) => toString(value)'), { toString: 'operation:route' });
  assert.equal(normalized.body.callee.name, 'operation:route');
});
