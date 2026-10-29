import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, cp, readFile, writeFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { APP_ROOT, OUTPUT, verify } from "../scripts/original-portfolio-read-policies.mjs";

test("--check rejects a portfolio read-policy contract whose bytes differ from the --write output", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "pump-policies-bytes-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const contract = await verify();
  const files = new Set(["evidence/web/manifest.json", "recovered/modules.json", OUTPUT]);
  JSON.stringify(contract, (key, value) => {
    if (key === "source" && typeof value === "string" && value.startsWith("evidence/")) files.add(value);
    return value;
  });
  for (const file of files) {
    await mkdir(path.dirname(path.join(root, file)), { recursive: true });
    await cp(path.join(APP_ROOT, file), path.join(root, file));
  }
  const written = JSON.stringify(contract, null, 2) + "\n";
  assert.equal(await readFile(path.join(root, OUTPUT), "utf8"), written);
  await verify(root);
  // Same values, different bytes: VALIDATION.json pins the sha256 of the written bytes.
  const { schemaVersion, ...rest } = JSON.parse(written);
  for (const variant of [JSON.stringify(contract), JSON.stringify({ ...rest, schemaVersion }, null, 2) + "\n"]) {
    await writeFile(path.join(root, OUTPUT), variant);
    await assert.rejects(verify(root), /portfolio policy contract is stale/);
  }
});
