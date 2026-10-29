/**
 * Spot-only chainId admission for the positions read model.
 *
 * The developer contract marks chainId 0 as a HyperCore or ton:-239 row, and
 * POSITIONS.md says admission rejects unsupported asset classes/chains. The
 * `chain`/`hlcore:` checks caught labelled rows, but a row that omits `chain`
 * and carries chainId 0 (or a negative id) was admitted and served as a spot
 * position. Solana/EVM spot rows carry positive chain ids, as in user-trades.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { PositionsStore, type PositionFacts } from "../src/positions-store.js";

const now = "2026-10-28T00:00:00.000Z";
const dataset = (chainId: number | null) => {
  const facts: PositionFacts = {
    coinMint: "BTC",
    chainId,
    isExited: false,
    walletAddress: "synthetic-wallet-a",
    amountHeld: 5,
    pnlUsd: null,
    pnlPercentage: null,
    costBasisAmount: null,
    costBasisUsd: null,
    amountBoughtUsd: null,
    amountBought: null,
    tokenPriceUsd: null,
  };
  return {
    schemaVersion: 1,
    dataSource: "synthetic",
    observedAt: now,
    subjects: [
      {
        kind: "person",
        id: "person-a",
        aliases: ["synthetic-wallet-a"],
        positions: [{ facts }],
      },
    ],
    coins: [],
    callouts: [],
    updates: [],
  };
};

test("unlabelled chainId 0 and negative ids are not admitted as spot rows", () => {
  for (const chainId of [0, -239])
    assert.throws(
      () => new PositionsStore(dataset(chainId)),
      /chainId/,
      `chainId=${chainId}`,
    );
});

test("positive spot chain ids are still admitted and served", () => {
  const store = new PositionsStore(dataset(101));
  assert.equal(store.portfolio("person-a")?.positions.length, 1);
});
