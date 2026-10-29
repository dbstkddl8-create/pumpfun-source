import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { buildApp } from './with-api-key.js';
import { SYNTHETIC_POSTS_SEED, decodeCursor, encodeCursor } from '../src/posts-store.js';

const root = SYNTHETIC_POSTS_SEED.find(p => !p.deleted && !p.hidden && p.kind === 'root')!;
// A well-formed tuple cursor whose base64url text is exactly `length` characters.
const cursorOfLength = (length: number): string => {
  const prefix = JSON.stringify(['2024-01-01T00:00:00.000Z', '']).length;
  const bytes = Math.floor((length * 3) / 4);
  const cursor = encodeCursor({ createdAt: '2024-01-01T00:00:00.000Z', postId: 'x'.repeat(bytes - prefix) });
  assert.equal(cursor.length, length);
  return cursor;
};

test('reply and quote cursors are bounded by the declared maxLength', async () => {
  const specification = JSON.parse(readFileSync(new URL('../../../contracts/developer.openapi.json', import.meta.url), 'utf8'));
  const app = buildApp([]);
  try {
    for (const relation of ['replies', 'quotes']) {
      const cursor = specification.paths[`/posts/{postId}/${relation}`].get.parameters
        .find((parameter: { name: string }) => parameter.name === 'cursor');
      assert.equal(cursor.schema.maxLength, 200);
      const atLimit = await app.inject(`/v1/posts/${root.postId}/${relation}?cursor=${cursorOfLength(200)}`);
      assert.equal(atLimit.statusCode, 200);
      const overLimit = await app.inject(`/v1/posts/${root.postId}/${relation}?cursor=${cursorOfLength(202)}`);
      assert.equal(overLimit.statusCode, 400);
      assert.deepEqual(overLimit.json().error, 'INVALID_CURSOR');
    }
  } finally {
    await app.close();
  }
  assert.equal(decodeCursor(cursorOfLength(202)), null);
  // Every cursor the seed can emit stays within the bound and still decodes.
  for (const post of SYNTHETIC_POSTS_SEED) assert.notEqual(decodeCursor(encodeCursor(post)), null);
});
