import test from "node:test";
import assert from "node:assert/strict";
import { buildApp } from "../src/app.js";
import { UserTradesStore, type UserTradesDataset } from "../src/user-trades-store.js";

const headers = { authorization: `Bearer pf_live_${"A".repeat(49)}` }; // Synthetic shape only.

function dataset(): UserTradesDataset {
  return {
    schemaVersion: 1, dataSource: "synthetic", observedAt: "2026-10-29T00:00:00Z",
    users: [], wallets: [{ address: "synthetic-wallet", chainId: 101, userId: null }],
    rows: [], coins: [], traders: [],
  };
}

test("chain lanes reject chainId and transfers as 400 before the 501 lane gate", async () => {
  const app = buildApp([], { userTradesStore: new UserTradesStore(dataset()) });
  try {
    const status = async (query: string) =>
      (await app.inject({ url: `/v1/user-trades/synthetic-wallet?${query}`, headers })).statusCode;
    for (const chain of ["ton:-239", "starknet:SN_MAIN", "near:mainnet"]) {
      assert.equal(await status(`chain=${chain}&chainId=101`), 400, chain);
      assert.equal(await status(`chain=${chain}&types=transfers`), 400, chain);
      assert.equal(await status(`chain=${chain}&types=trades,transfers`), 400, chain);
      // Valid lane requests still report the unmodeled lane explicitly.
      assert.equal(await status(`chain=${chain}`), 501, chain);
      assert.equal(await status(`chain=${chain}&types=trades`), 501, chain);
    }
  } finally {
    await app.close();
  }
});
