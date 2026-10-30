import test from 'node:test';
import assert from 'node:assert/strict';
import { buildApp } from './with-api-key.js';
import { PostStore, SYNTHETIC_POSTS_SEED, type RawPost } from '../src/posts-store.js';

// The batch read's declared ids pattern admits A-F, and UUIDs compare
// case-insensitively, so an uppercase spelling names the same stored post.
const original = SYNTHETIC_POSTS_SEED[0].postId;
const lower = 'abcdef01-2345-4678-89ab-cdef01234567';
const seed = JSON.parse(JSON.stringify(SYNTHETIC_POSTS_SEED).split(original).join(lower)) as RawPost[];

test('post batches resolve uppercase spellings of stored lowercase UUIDs', async () => {
  const app = buildApp([], { postStore: new PostStore(seed) });
  try {
    const baseline = await app.inject(`/v1/posts?ids=${lower}`);
    assert.equal(baseline.statusCode, 200);
    assert.deepEqual(baseline.json().posts.map((post: { postId: string }) => post.postId), [lower]);

    const upper = await app.inject(`/v1/posts?ids=${lower.toUpperCase()}`);
    assert.equal(upper.statusCode, 200);
    assert.deepEqual(upper.json().posts, baseline.json().posts);

    // Two spellings of one UUID are duplicates and collapse to one row.
    const mixed = await app.inject(`/v1/posts?ids=${lower},${lower.toUpperCase()}`);
    assert.equal(mixed.statusCode, 200);
    assert.deepEqual(mixed.json().posts, baseline.json().posts);
  } finally {
    await app.close();
  }
});
