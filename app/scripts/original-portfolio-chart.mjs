import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { openCorpus, findNodes, exactlyOne, propertyName, objectProperty, literal } from "./original-contracts/source.mjs";

export const APP_ROOT = fileURLToPath(new URL("..", import.meta.url));
export const OUTPUT = "reconstruction/portfolio-chart/contract.json";
const CHART = "evidence/web/objects/910b5c033a62f9b1.js";
const HTTP = "evidence/web/objects/01ad4f413e529b60.js";
const CONFIG = "evidence/web/objects/1e479323ffe53c14.js";
const EXPECTED = [
  [58159, CHART, "a3d13f1106ec2535401f560c022714d49cd3bfeef0b83a80fd0f24a4119c3b50"],
  [674121, CHART, "6e1b58533d14ec0e8e6bce130af04286c898968099c8758ec5668faaa0be82ef"],
  [759257, CONFIG, "e1c207697339004b48f6baa9f81f34e7644686ee424616b553e55b23c659b855"],
  [503630, CONFIG, "df5a12d4b76158889dd38a02d0d9afc0d0405065772b589c9cadf9806422d0e7"],
  [30181, HTTP, "fbae4e508e6c986c68209d975d3eea247718d478272089a60504b776074e2413"],
  [898661, "evidence/web/objects/2b47dd0b38a1608f.js", "9015e4bad4b1f0bb4b245e446689d9b7e939b3ba922044c82dcd9e8d5f3d9ed5"],
];
function declaration(factory, name) {
  return exactlyOne(findNodes(factory.node, n => n.type === "VariableDeclarator" && n.id?.name === name), `declaration ${name}`).init;
}
function simple(node) {
  if (node.type === "ArrayExpression") return node.elements.map(simple);
  return literal(node);
}

export async function recover(root = APP_ROOT) {
  const corpus = await openCorpus(root), factories = new Map();
  for (const [id, source, hash] of EXPECTED) {
    const f = await corpus.factory(id, { source });
    assert.equal(f.provenance.sha256, hash, `review required for changed factory ${id}`);
    factories.set(id, f);
  }
  const reader = factories.get(58159), retry = declaration(reader, "o");
  const retryFields = Object.fromEntries(retry.properties.filter(p => propertyName(p.key) !== "shouldRetry")
    .map(p => [propertyName(p.key), simple(p.value)]));
  const getter = declaration(reader, "c"), schema = declaration(reader, "u");
  const operation = exactlyOne(findNodes(getter, n => n.type === "StringLiteral" && n.value === "GET /portfolio-summary/chart"), "chart operation");
  const timeout = exactlyOne(findNodes(getter, n => n.type === "ObjectProperty" && propertyName(n.key) === "timeout"), "timeout");
  const imported = findNodes(reader.node, n => n.type === "CallExpression" && n.callee?.object?.name === reader.runtime &&
    propertyName(n.callee.property) === "i" && n.arguments[0]?.type === "NumericLiteral").map(n => n.arguments[0].value);
  assert.deepEqual(imported, [812768, 820984, 955871, 415809, 514287, 759257]);

  // A merged inventory variant can have multiple identical registrations in one
  // physical chunk. Resolve each *actual* alias registration, never choose the
  // first origin just because its content hash happens to match.
  const capture = await corpus.javascript(CHART), aliases = [];
  for (const id of [820984, 955871, 415809, 514287]) {
    const registration = exactlyOne(capture.factories.filter(f => f.ids.includes(id)), `schema alias ${id}`);
    const witness = capture.witness(registration.node, `actual schema alias ${id}`);
    assert.equal(witness.sha256, "ba8acac696188ebf2b0f8a345344d353b8a347f40edce3afee2ddc45d860914c");
    assert.ok(corpus.index.modules.some(v => v.sha256 === witness.sha256 && v.ids.includes(id) &&
      v.origins.some(o => o.source === CHART && o.start === registration.node.start && o.end === registration.node.end)));
    const target = exactlyOne(findNodes(registration.node, n => n.type === "CallExpression" && n.callee?.property?.name === "i"), `schema alias import ${id}`);
    assert.equal(target.arguments[0].value, 599565);
    aliases.push({ id, ...witness, target: 599565 });
  }
  const library = await corpus.factory(599565, { source: "evidence/web/objects/06e532443c8db686.js" });
  assert.equal(library.provenance.sha256, "375bf1a7298ca40a088210d7036d5422547ed59153f205de430426824b85caaf");
  const config = factories.get(503630);
  const configExports = exactlyOne(findNodes(config.node, n => n.type === "ArrayExpression" && n.elements.some(e => e?.value === "R")), "origin export");
  const origin = configExports.elements[configExports.elements.findIndex(n => n?.value === "R") + 2].body.value;
  assert.equal(origin, "https://frontend-api-v3.pump.fun");
  const consumers = corpus.index.modules.filter(v => v.sha256 === factories.get(674121).provenance.sha256);
  return {
    schemaVersion: 1, authority: "static captured client workflow; no bundle execution or native backend qualification",
    anchors: corpus.anchors,
    operation: { key: operation.value, feature: "/portfolio", source: reader.witness(operation, "used chart operation"),
      websiteOrigin: origin, developerApiOrigin: "https://api.pump.fun/v1", interchangeableHostsEstablished: false,
      query: ["user", "period"], constructorOptions: ["timeout", "retry", "signal"], timeoutMs: literal(timeout.value),
      inputValidationOrDefaultInReader: false, credentials: "same-origin", headers: { accept: "application/json", "x-pump-source": "WEB", "x-pump-platform": "web" } },
    retry: { options: retryFields, callback: reader.witness(objectProperty(retry, "shouldRetry"), "exact retry callback"),
      computingBody: reader.witness(declaration(reader, "s"), "clone JSON computing predicate"),
      deferredValue: "undefined", stoppedValue: false, frameworkSchedulingReproduced: false },
    schema: { expression: reader.witness(schema, "used minimal response schema"),
      periods: ["1d", "1w", "1m", "all"], required: ["period", "points"], pointRequired: ["time", "value"],
      pointTypes: { time: "number", value: "number" }, topLevelPassthrough: true,
      parsedResultDiscarded: true, returnedResponseIdentityPreserved: true, libraryImplementationQualified: false,
      aliases, library: library.provenance },
    keys: { wallet: ["portfolioChart", "user", "period"], walletPrefix: ["portfolioChart", "user"],
      actualConsumer: { kind: "prefix invalidation", factory: factories.get(674121).provenance,
        inventoryVariantCount: consumers.length }, readUICallerEstablished: false },
    factories: [...factories.values()].map(f => f.provenance),
    qualifications: { nativeBackend: false, productionTraffic: false, uiIntegrated: false, featureCredit: false },
    limits: ["Injected parser and HTTPError retain dependency boundaries; original library runtimes are not executed or installed.",
      "Local HTTP adapter performs one attempt without Ky timeout, retry scheduling, error normalization or cookie jar.",
      "No prices, historical series, canonical wallet links, aggregation, authentication or PnL implementation."],
  };
}

export async function verify(root = APP_ROOT) {
  const fresh = await recover(root);
  // VALIDATION.json pins the contract's sha256, so compare the exact --write bytes.
  assert.equal(await readFile(path.join(root, OUTPUT), "utf8"), JSON.stringify(fresh, null, 2) + "\n", "portfolio chart contract is stale");
  return fresh;
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const mode = process.argv[2];
  if (mode === "--write") {
    const value = await recover();
    await mkdir(path.dirname(path.join(APP_ROOT, OUTPUT)), { recursive: true });
    await writeFile(path.join(APP_ROOT, OUTPUT), JSON.stringify(value, null, 2) + "\n");
    console.log(`Wrote ${OUTPUT}`);
  } else if (mode === "--check") {
    await verify(); console.log("Original portfolio chart source contract PASS");
  } else throw new Error("Use --write or --check");
}
