import assert from "node:assert/strict";
import { readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { analyzeFactory, buildGraph } from "../scripts/factory-graph/core.mjs";
import { fixture } from "./factory-graph-fixture.mjs";

test("recovered factories cannot carry extra top-level statements", async () => {
  assert.throws(
    () => analyzeFactory(`((e)=>{e.s(["v",0,1],2)});\nglobalThis.injected=1;\n`),
    /does not contain a top-level function expression/,
  );
  assert.throws(
    () => analyzeFactory(`globalThis.injected=1;\n((e)=>{e.s(["v",0,1],2)});\n`),
    /does not contain a top-level function expression/,
  );
  assert.throws(
    () => analyzeFactory(`"use strict";\n(function(runtime) { return this; });`),
    /does not contain a top-level function expression/,
  );

  const root = await fixture();
  try {
    const modules = JSON.parse(
      await readFile(join(root, "recovered/modules.json"), "utf8"),
    ).modules;
    const path = join(root, modules[0].path);
    await writeFile(path, `${await readFile(path, "utf8")}globalThis.injected = 1;\n`);
    await assert.rejects(buildGraph(root), /does not contain a top-level function expression/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
