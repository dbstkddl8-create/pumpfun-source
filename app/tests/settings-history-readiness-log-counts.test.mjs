import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const script = fileURLToPath(new URL("../scripts/verify-settings-history-readiness.mjs", import.meta.url));
const hash = (text) => createHash("sha256").update(text).digest("hex");
const trace = (next) => ({ event: "popstate", detail: { eventState: { next } } });

// The verifier checks the receipt folder beside its own location at import
// time, so each case imports a copy placed in a fresh minimal app tree. Empty
// trace inputs keep the run to saved files only.
async function verifyWithLog(log) {
  const app = mkdtempSync(path.join(tmpdir(), "settings-readiness-"));
  try {
    const folder = path.join(app, "research/settings-history-readiness-20261029");
    mkdirSync(folder, { recursive: true });
    mkdirSync(path.join(app, "scripts"));
    mkdirSync(path.join(app, "tests"));
    const copy = path.join(app, "scripts/verify-settings-history-readiness.mjs");
    copyFileSync(script, copy);
    const browser = "// browser producer\n";
    writeFileSync(path.join(app, "tests/settings_history_readiness.browser.mjs"), browser);
    writeFileSync(path.join(folder, "after-suite.log"), log);
    writeFileSync(path.join(folder, "initial-causal-trace.json"), JSON.stringify({ inputs: {}, results: [
      { mode: "light-original", closed: false, trace: [trace(null)] },
      { mode: "light-interactive", closed: true, trace: [trace(true)] },
    ] }));
    writeFileSync(path.join(folder, "causal-trace.json"), JSON.stringify({ scriptSha256: hash(browser), inputs: {}, results: [
      { mode: "light-interactive", closed: true, launcherFocused: true, streamPreserved: true, playbackVisible: true,
        final: { sidebar: "open" }, errors: [], external: [] },
    ] }));
    writeFileSync(path.join(folder, "verification.json"), JSON.stringify({ baseline: "0".repeat(40), files: { "after-suite.log": hash(log) },
      uniqueCoverage: { passed: 14, failed: 1, skipped: 0, wholeSuitePassClaimed: false } }));
    await import(pathToFileURL(copy).href);
  } finally {
    rmSync(app, { recursive: true, force: true });
  }
}

const summary = (failed, skipped, passed) =>
  `Escape and repeated reopening\n\n  ${failed} failed\n  ${skipped} did not run\n  ${passed} passed (15.6s)\n`;

test("the saved 9 passed / 1 failed / 5 did not run summary verifies", async () => {
  await verifyWithLog(summary(1, 5, 9));
});

test("summaries with different counts that merely end in the claimed digits are rejected", async () => {
  for (const [failed, skipped, passed] of [[1, 5, 19], [11, 5, 9], [1, 15, 9]]) {
    await assert.rejects(verifyWithLog(summary(failed, skipped, passed)), assert.AssertionError,
      `${failed} failed / ${skipped} did not run / ${passed} passed was accepted`);
  }
});
