import test from 'node:test';
import assert from 'node:assert/strict';
import { CalloutsStore } from '../src/callouts-store.js';

const observedAt = '2026-10-29T00:00:00.000Z';
const future = '2026-10-30T00:00:00.000Z';
function dataset(): any {
  return {
    schemaVersion: 1, dataSource: 'synthetic', observedAt,
    authors: [{ authorId: 'owner', userName: 'Owner', profileImage: null, isVerified: false,
      verifiedBadgeVisible: false, accountKind: 'person', xUsername: null, xFollowerCount: 0 }],
    callouts: [{
      calloutId: 'root', authorId: 'owner', hidden: false, deleted: false,
      facts: { calloutId: 'root', userId: 'w', coinMint: 'm', marketCap: 10, calloutPrice: 0,
        calloutPriceUsd: 1, multiple: 1, createdAt: 0, maxPriceSol: 0, maxPriceUsd: 1, likes: 0,
        repostCount: 0, quoteCount: 0, updateCount: 0, commentCount: 0, replyCount: 0,
        maxMultiplier: null, maxMultiplierAt: null, mediaUrl: null, quotedCalloutId: null },
      quoteFacts: { calloutId: 'root', calledOutAtMcap: 10, multiple: 1, thesis: 't', mediaUrl: null,
        calloutTimestamp: observedAt, likes: 0, updateCount: 0, commentCount: 0, replyCount: 0,
        maxMultiplier: null, maxMultiplierAt: null, calloutPrice: 1, repostCount: 0, quoteCount: 0,
        actingUserId: null, actingUser: null },
    }],
    updates: [],
  };
}

test('callout and quote instants cannot postdate the observation checkpoint', () => {
  const quoted = dataset();
  quoted.callouts[0].quoteFacts.calloutTimestamp = future;
  assert.throws(() => new CalloutsStore(quoted), /observedAt/);
  const quotedMax = dataset();
  quotedMax.callouts[0].quoteFacts.maxMultiplierAt = future;
  assert.throws(() => new CalloutsStore(quotedMax), /observedAt/);
  const factsMax = dataset();
  factsMax.callouts[0].facts.maxMultiplierAt = future;
  assert.throws(() => new CalloutsStore(factsMax), /observedAt/);
  // Instants at or before the checkpoint, and unknown ones, still load.
  const atCheckpoint = dataset();
  atCheckpoint.callouts[0].facts.maxMultiplierAt = observedAt;
  atCheckpoint.callouts[0].quoteFacts.maxMultiplierAt = observedAt;
  assert.doesNotThrow(() => new CalloutsStore(atCheckpoint));
  const unknown = dataset();
  unknown.callouts[0].quoteFacts.calloutTimestamp = null;
  assert.doesNotThrow(() => new CalloutsStore(unknown));
});
