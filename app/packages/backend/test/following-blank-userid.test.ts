import test from 'node:test';
import assert from 'node:assert/strict';
import { FollowingStore } from '../src/following-store.js';
import { UserStore } from '../src/users-store.js';

test('follow rows fall back to the wallet when the stored userId is blank', () => {
  const rows = new UserStore().list({}).slice(0, 2);
  // UserStore treats a blank userId as absent: it is not indexed as an identity.
  rows[0].address = 'blank-id-wallet';
  rows[0].userId = '';
  rows[1].address = 'target-wallet';
  rows[1].userId = 'target-user';
  const users = new UserStore(rows);
  assert.equal(users.getById(''), undefined);
  const store = new FollowingStore(users, [
    { follower_id: 'blank-id-wallet', following_id: 'target-user', timestamp: 1 },
    { follower_id: 'target-user', following_id: 'blank-id-wallet', timestamp: 2 },
  ]);
  for (const result of [store.followersOf('target-user'), store.followingOf('target-user')]) {
    assert.equal(result.length, 1);
    assert.equal(result[0].userId, 'blank-id-wallet');
    assert.equal(result[0].user_id, 'blank-id-wallet');
  }
});
