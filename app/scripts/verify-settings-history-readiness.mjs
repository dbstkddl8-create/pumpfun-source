// Check saved finite browser evidence; this does not rerun or attest a browser.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const app = fileURLToPath(new URL("..", import.meta.url));
const folder = path.join(app, "research/settings-history-readiness-20261029");
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const json = async (name) =>
  JSON.parse(await readFile(path.join(folder, name)));
const record = await json("verification.json");
assert.match(record.baseline, /^[a-f0-9]{40}$/);
for (const [name, sha] of Object.entries(record.files)) {
  assert.match(name, /^[A-Za-z0-9._-]+$/);
  assert.equal(
    hash(await readFile(path.join(folder, name))),
    sha,
    `stale ${name}`,
  );
}
const initial = await json("initial-causal-trace.json");
for (const [relative, sha] of Object.entries(initial.inputs)) {
  assert.ok(!relative.includes(".."));
  const bytes = execFileSync(
    "git",
    ["show", `${record.baseline}:app/packages/frontend/${relative}`],
    {
      cwd: path.resolve(app, ".."),
      env: { ...process.env, GIT_NO_LAZY_FETCH: "1" },
    },
  );
  assert.equal(hash(bytes), sha, `historical input ${relative}`);
}
const current = await json("causal-trace.json");
assert.equal(
  current.scriptSha256,
  hash(
    await readFile(
      path.join(app, "tests/settings_history_readiness.browser.mjs"),
    ),
  ),
);
// The portable run is bound to the qualified PR head, not the live worktree:
// later main commits may legitimately change these files, which invalidates
// the run's scope (a fresh run is required) but not the saved receipt.
const qualifiedHead = "56bf34935a32b3a744502358efb8116f76c4f8fb";
for (const [relative, sha] of Object.entries(current.inputs)) {
  assert.ok(!relative.includes(".."));
  const bytes = execFileSync(
    "git",
    ["show", `${qualifiedHead}:app/packages/frontend/${relative}`],
    {
      cwd: path.resolve(app, ".."),
      env: { ...process.env, GIT_NO_LAZY_FETCH: "1" },
    },
  );
  assert.equal(hash(bytes), sha, `qualified-head input ${relative}`);
}
const oldOrder = initial.results.find((r) => r.mode === "light-original");
const interactive = initial.results.find((r) => r.mode === "light-interactive");
assert.equal(oldOrder.closed, false);
assert.equal(
  oldOrder.trace.find((r) => r.event === "popstate").detail.eventState.next,
  null,
);
assert.equal(interactive.closed, true);
assert.equal(
  interactive.trace.find((r) => r.event === "popstate").detail.eventState.next,
  true,
);
const qualified = current.results.find((r) => r.mode === "light-interactive");
assert.ok(
  qualified.closed &&
    qualified.launcherFocused &&
    qualified.streamPreserved &&
    qualified.playbackVisible &&
    qualified.final.sidebar === "open",
);
assert.ok(
  current.results.every(
    (r) => r.errors.length === 0 && r.external.length === 0,
  ),
);
assert.deepEqual(record.uniqueCoverage, {
  passed: 14,
  failed: 1,
  skipped: 0,
  wholeSuitePassClaimed: false,
});
const after = await readFile(path.join(folder, "after-suite.log"), "utf8");
// Whole summary counts: "19 passed" or "11 failed" must not satisfy the claim.
assert.match(after, /^ *9 passed\b/m);
assert.match(after, /^ *1 failed *$/m);
assert.match(after, /^ *5 did not run *$/m);
assert.match(after, /Escape and repeated reopening/);
console.log(
  JSON.stringify({
    result: "PASS",
    finiteSettingsCasesPassed: 14,
    separateKnownEscapeFailure: 1,
    browserRerun: false,
    originalProductFailureClaimed: false,
  }),
);
