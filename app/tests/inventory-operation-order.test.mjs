import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { buildInventory } from "../scripts/inventory.mjs";

// Captured operations whose order differs under Czech collation, where "ch"
// sorts after "h": the checked-in contract lists GET /check before GET /coins.
const source = 'const routes = ["GET /coins", "GET /check/{address}", "GET /changelog"];\n';

async function operationsWithDefaultLocale(locale) {
  const root = mkdtempSync(path.join(tmpdir(), "inventory-order-"));
  const localeCompare = String.prototype.localeCompare;
  // A process started with LANG=cs_CZ.UTF-8 has this default collation.
  String.prototype.localeCompare = function (that, locales, options) {
    return localeCompare.call(this, that, locales ?? locale, options);
  };
  try {
    mkdirSync(path.join(root, "evidence/web/objects"), { recursive: true });
    writeFileSync(path.join(root, "evidence/web/objects/routes"), source);
    writeFileSync(path.join(root, "evidence/web/manifest.json"), JSON.stringify({ records: [{
      url: "https://pump.fun/_next/static/chunks/routes.js", status: 200, path: "evidence/web/objects/routes",
      sha256: createHash("sha256").update(source).digest("hex"),
    }] }));
    const { reportFiles } = await buildInventory(root);
    return JSON.parse(reportFiles.get("contracts/internal-operations.json")).operations.map((entry) => entry.operation);
  } finally {
    String.prototype.localeCompare = localeCompare;
    rmSync(root, { recursive: true, force: true });
  }
}

test("internal operation order does not depend on the process default locale", async () => {
  const expected = ["GET /changelog", "GET /check/{address}", "GET /coins"];
  assert.deepEqual(await operationsWithDefaultLocale("en"), expected);
  assert.deepEqual(await operationsWithDefaultLocale("cs"), expected);
});
