import assert from "node:assert/strict";
import { test } from "node:test";
import { buildApp } from "../src/app.js";

const ROUTE = "/services/frontend/home-feed";

test("ranked feed rejects malformed filters as 400 before the personalization 501 gate", async () => {
  const app = buildApp();
  try {
    const cases = [
      [`${ROUTE}?userId=someone&chain=nope`, "INVALID_CHAIN"],
      [`${ROUTE}?platform=APP&chains=solana,solana`, "INVALID_QUERY_LIST"],
      [`${ROUTE}?session_id=s&minMarketCapUsd=abc`, "INVALID_NUMBER"],
      [
        `${ROUTE}?includeFollowedHolders=true&minCostBasisUsd=10&maxCostBasisUsd=9`,
        "CONTRADICTORY_BOUNDS",
      ],
    ] as const;
    for (const [url, expected] of cases) {
      const response = await app.inject(url);
      assert.equal(response.statusCode, 400, url);
      assert.equal(response.json().error, expected, url);
    }
    // Well-formed filters keep the existing personalization boundary.
    const valid = await app.inject(`${ROUTE}?userId=someone&chain=solana`);
    assert.equal(valid.statusCode, 501);
    assert.equal(valid.json().error, "PERSONALIZED_FEED_UNAVAILABLE");
  } finally {
    await app.close();
  }
});
