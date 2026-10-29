import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  openCorpus,
  findNodes,
  exactlyOne,
  propertyName,
  literal,
} from "./original-contracts/source.mjs";

export const APP_ROOT = fileURLToPath(new URL("..", import.meta.url));
export const OUTPUT = "reconstruction/positions-by-mint/contract.json";
const EXPECTED = [
  [
    384886,
    "evidence/web/objects/a73dd4b5aeff6202.js",
    "9c9f618b76fb17141d8f9e484d08c037906da8c060c223efcd32bfee111f54cb",
  ],
  [
    26077,
    "evidence/web/objects/020facfab961bf67.js",
    "773b099ebb0e3ef6d31d97927908f2d71c9b2c25583c0608c0a1c2e5147648a6",
  ],
  [
    646908,
    "evidence/web/objects/1e479323ffe53c14.js",
    "719f637fc436bde35bcaa1da5eac3057212d49b84331e27068450218041eb6c0",
  ],
  [
    768359,
    "evidence/web/objects/4da5ade5abc4fe3f.js",
    "a892f6e2b82646fc0744e14273ab5fd6a2bec6e032a8b991e323c41bec50b20d",
  ],
  [
    759257,
    "evidence/web/objects/1e479323ffe53c14.js",
    "e1c207697339004b48f6baa9f81f34e7644686ee424616b553e55b23c659b855",
  ],
  [
    503630,
    "evidence/web/objects/1e479323ffe53c14.js",
    "df5a12d4b76158889dd38a02d0d9afc0d0405065772b589c9cadf9806422d0e7",
  ],
  [
    30181,
    "evidence/web/objects/01ad4f413e529b60.js",
    "fbae4e508e6c986c68209d975d3eea247718d478272089a60504b776074e2413",
  ],
  [
    898661,
    "evidence/web/objects/2b47dd0b38a1608f.js",
    "9015e4bad4b1f0bb4b245e446689d9b7e939b3ba922044c82dcd9e8d5f3d9ed5",
  ],
];
function declaration(factory, name) {
  return exactlyOne(
    findNodes(
      factory.node,
      (n) => n.type === "VariableDeclarator" && n.id?.name === name,
    ),
    `declaration ${factory.id}.${name}`,
  ).init;
}
export async function recover(root = APP_ROOT) {
  const corpus = await openCorpus(root),
    fs = new Map();
  for (const [id, source, hash] of EXPECTED) {
    const f = await corpus.factory(id, { source });
    assert.equal(
      f.provenance.sha256,
      hash,
      `review required for changed factory ${id}`,
    );
    fs.set(id, f);
  }
  const f = fs.get(384886),
    threshold = fs.get(26077),
    chain = fs.get(646908),
    consumer = fs.get(768359);
  const exports = exactlyOne(
    findNodes(
      threshold.node,
      (n) => n.type === "ArrayExpression" && n.elements[0]?.value === "N",
    ),
    "threshold export",
  );
  const timeout = exactlyOne(
    findNodes(
      f.node,
      (n) => n.type === "ObjectProperty" && propertyName(n.key) === "timeout",
    ),
    "operation timeout",
  );
  const operation = exactlyOne(
    findNodes(
      f.node,
      (n) =>
        n.type === "StringLiteral" &&
        n.value === "GET /user-positions/{userId}",
    ),
    "operation",
  );
  const hook = exactlyOne(
    findNodes(
      f.node,
      (n) =>
        n.type === "ObjectProperty" && propertyName(n.key) === "afterResponse",
    ),
    "afterResponse hook",
  );
  const used = exactlyOne(
    findNodes(
      consumer.node,
      (n) =>
        n.type === "CallExpression" &&
        n.callee?.type === "SequenceExpression" &&
        n.callee.expressions[1]?.type === "MemberExpression" &&
        n.callee.expressions[1].object?.name === "I" &&
        n.callee.expressions[1].property?.name === "X",
    ),
    "actual portfolio use of row normalizer",
  );
  const variants = corpus.index.modules
    .filter((v) => v.ids.includes(768359))
    .map((v) => ({ sha256: v.sha256, origins: v.origins }));
  const namespaces = ["i", "a", "d"].map((name) =>
    literal(declaration(chain, name)),
  );
  assert.deepEqual(namespaces, [
    "ton:-239",
    "starknet:SN_MAIN",
    "near:mainnet",
  ]);
  return {
    schemaVersion: 1,
    authority:
      "bounded static captured client; not native API or full portfolio qualification",
    anchors: corpus.anchors,
    operation: {
      key: operation.value,
      feature: "/portfolio",
      source: f.witness(operation, "used mint position read"),
      websiteOrigin: "https://frontend-api-v3.pump.fun",
      developerApiHostInterchangeable: false,
      timeoutMs: literal(timeout.value),
      timeoutPlacement: "operation options",
      constructorCalledPerChunk: true,
      mints:
        "truthy filter, case-sensitive Set in input order, at most200 per chunk",
      updatesLimit: 0,
      concurrency:
        "Promise.all, flatten chunk order, reject on any chunk failure without canceling siblings",
      hook: f.witness(hook.value, "404 replacement and non-ok error"),
      responseSchemaValidation: false,
    },
    normalization: {
      threshold: literal(exports.elements[2]),
      thresholdSource: threshold.witness(exports.elements[2], "used26077.N"),
      invalid: "typeof number and (not finite or abs(value)>threshold)",
      valueFields: ["valueUsd", "pnlUsd"],
      rejectedUndefined: ["valueUsd", "tokenPriceUsd"],
      rejectedNull: ["pnlUsd", "pnlPercentage", "coin.marketCapUsd"],
      rejectedFlag: "servedQuoteRejected",
      coinOnlyRejection:
        "clone coin with marketCapUsd:null; retain all other row fields",
      admittedRowsRetainIdentity: true,
      source: f.witness(declaration(f, "r"), "complete normalizer"),
    },
    helpers: {
      readOne: "first case-insensitive coinMint match, otherwise null",
      map: "truthy mint, lower-case key, last row wins",
      lookup: "falsy mint returns undefined; otherwise lower-case lookup",
      namespaces,
      namespaceAppliedOnlyByKeyHelper: true,
      coinKeyCasePreserved: true,
    },
    actualConsumer: {
      factory: consumer.provenance,
      call: consumer.witness(used, "used528766.X positions normalization"),
      availableFactoryVariants: variants,
      fullReactHookReconstructed: false,
      routeReachabilityEstablished: false,
    },
    factories: [...fs.values()].map((f) => f.provenance),
    qualifications: {
      nativeBackend: false,
      productionTraffic: false,
      uiIntegrated: false,
      featureCredit: false,
    },
    limits: [
      "Local HTTP adapter is single-attempt; original Ky scheduling, timeout enforcement, contract-error normalization and cookies remain outside qualification.",
      "Original numeric guard is client quote admission, not price calculation, valuation correctness or numeric response-schema validation.",
      "No full React hook, native holdings, wallet authentication, perps product, RPC/indexer, PnL calculation or portfolio UI is implemented.",
    ],
  };
}
export async function verify(root = APP_ROOT) {
  const value = await recover(root);
  // VALIDATION.json pins the contract's sha256, so compare the exact --write bytes.
  assert.equal(
    await readFile(path.join(root, OUTPUT), "utf8"),
    JSON.stringify(value, null, 2) + "\n",
    "positions-by-mint contract is stale",
  );
  return value;
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  if (process.argv[2] === "--write") {
    const value = await recover();
    await mkdir(path.dirname(path.join(APP_ROOT, OUTPUT)), { recursive: true });
    await writeFile(
      path.join(APP_ROOT, OUTPUT),
      JSON.stringify(value, null, 2) + "\n",
    );
    console.log(`Wrote ${OUTPUT}`);
  } else if (process.argv[2] === "--check") {
    await verify();
    console.log("Original positions-by-mint source contract PASS");
  } else throw new Error("Use --write or --check");
}
