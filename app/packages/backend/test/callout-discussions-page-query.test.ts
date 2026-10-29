import { test } from "node:test";
import assert from "node:assert/strict";
import {
  CalloutDiscussionsStore,
  CalloutDiscussionError,
} from "../src/callout-discussions-store.js";

// Query parsing runs before any dataset read, so no materialization is needed.
const list = (query: string) =>
  CalloutDiscussionsStore.prototype.list.call(
    {} as CalloutDiscussionsStore,
    "callout",
    new URLSearchParams(query),
  );
const rejects = (query: string, status: number, reason: string) =>
  assert.throws(
    () => list(query),
    (error: unknown) =>
      error instanceof CalloutDiscussionError &&
      error.status === status &&
      error.reason === reason,
    query,
  );

test("malformed page values are 400 before the ranking 501 gate", () => {
  for (const page of ["abc", "-1", "1.5", "01", "", "9007199254740992"])
    rejects(`page=${page}`, 400, "CALLOUT_DISCUSSION_QUERY_INVALID");
});

test("well-formed page values still reach the ranking 501 gate", () => {
  for (const page of ["0", "3", "9007199254740991"])
    rejects(`page=${page}`, 501, "CALLOUT_DISCUSSION_RANKING_UNAVAILABLE");
});
