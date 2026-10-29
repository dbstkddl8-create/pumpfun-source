import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  APP_ROOT,
  compareInventory,
} from "../scripts/original-contract-http-errors.mjs";

test("inventory comparison rejects an index with a different range encoding", async (t) => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "http-errors-inventory-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const index = JSON.parse(
    await readFile(path.join(APP_ROOT, "recovered/modules.json")),
  );
  const expandedPath = path.join(directory, "expanded.json");
  await writeFile(expandedPath, JSON.stringify(index));
  assert.equal((await compareInventory(expandedPath)).completeEntriesEqual, true);
  // Same selected start/end numbers mean different source spans under
  // another encoding, so equal entries are not comparable evidence.
  index.rangeEncoding = "UTF-8 byte half-open offsets";
  await writeFile(expandedPath, JSON.stringify(index));
  await assert.rejects(compareInventory(expandedPath), /range encoding/);
  delete index.rangeEncoding;
  await writeFile(expandedPath, JSON.stringify(index));
  await assert.rejects(compareInventory(expandedPath), /range encoding/);
});
