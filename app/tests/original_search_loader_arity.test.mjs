import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parse } from '@babel/parser';
import { decodeSearchLoader } from '../scripts/original-search-contract.mjs';

const fixture = (text) => ({ runtime: 's', node: parse(`(${text})`).program.body[0].expression });
const source = 's=>{s.v(t=>Promise.all(["chunk.js"].map(x=>s.l(x))).then(()=>t(238128)))}';

test('loader grammar accepts the exact captured one-callback shape', () => {
  const decoded = decodeSearchLoader(fixture(source));
  assert.deepEqual([decoded.chunks, decoded.targetId], [['chunk.js'], 238128]);
});

test('loader grammar rejects a rejection handler that swallows chunk load failures', () => {
  assert.throws(() => decodeSearchLoader(fixture(source.replace('t(238128))', 't(238128),()=>{})'))), /loader then/);
});

test('loader grammar rejects extra arguments to the runtime chunk loader', () => {
  assert.throws(() => decodeSearchLoader(fixture(source.replace('s.l(x)', 's.l(x,1)'))), /runtime.l/);
});
