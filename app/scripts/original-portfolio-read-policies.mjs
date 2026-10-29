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
export const OUTPUT = "reconstruction/portfolio-read-policies/contract.json";
const EXPECTED = [
  [
    261756,
    "evidence/web/objects/4fd6e792e7a336d9.js",
    "4ac26c6ebefd39ced0f7565c26fa2820ffa4777ef16a0ee73d9c55dfbba7c2b0",
  ],
  [
    947305,
    "evidence/web/objects/4fd6e792e7a336d9.js",
    "14c50390a5c67dc9aad08d71bdcc42e1413c5601130c5d048f34bc755f0bffe1",
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
  [
    150430,
    "evidence/web/objects/1861f564fee26935.js",
    "ac21ce2c27a6b1af46a9445da81d69ed171198284da7107bb22b6ffabde99655",
  ],
  [
    400466,
    "evidence/web/objects/13c13db9eb86191b.js",
    "b55e1d78341162edfc6c5ff1ba32c4b4faa3d0ade6de3a39f440fe39f2e9e5dd",
  ],
];
function numericProperty(f, name) {
  return literal(
    exactlyOne(
      findNodes(
        f.node,
        (n) => n.type === "ObjectProperty" && propertyName(n.key) === name,
      ),
      name,
    ).value,
  );
}
function importedCalls(f, id, property) {
  const item = exactlyOne(
    findNodes(
      f.node,
      (n) =>
        n.type === "VariableDeclarator" &&
        n.init?.type === "CallExpression" &&
        n.init.arguments[0]?.value === id,
    ),
    `import${id}`,
  );
  return findNodes(
    f.node,
    (n) =>
      n.type === "CallExpression" &&
      n.callee?.type === "SequenceExpression" &&
      n.callee.expressions[1]?.object?.name === item.id.name &&
      propertyName(n.callee.expressions[1]?.property) === property,
  ).map((n) => ({ text: f.text(n), ...f.witness(n, `used${id}.${property}`) }));
}
export async function recover(root = APP_ROOT) {
  const corpus = await openCorpus(root),
    fs = [];
  for (const [id, source, hash] of EXPECTED) {
    const f = await corpus.factory(id, { source });
    assert.equal(
      f.provenance.sha256,
      hash,
      `review required for changed factory ${id}`,
    );
    fs.push(f);
  }
  const dust = fs[0],
    spam = fs[1],
    getter = exactlyOne(
      findNodes(
        dust.node,
        (n) => n.type === "FunctionDeclaration" && n.id?.name === "s",
      ),
      "dust getter",
    );
  assert.equal(
    findNodes(
      getter,
      (n) =>
        n.type === "ObjectProperty" &&
        ["params", "query", "body"].includes(propertyName(n.key)),
    ).length,
    0,
  );
  const getterSpam = exactlyOne(
    findNodes(
      spam.node,
      (n) => n.type === "ArrowFunctionExpression" && n.async,
    ),
    "spam getter",
  );
  const normalizers = [];
  for (const [source, hash] of [
    [
      "evidence/web/objects/4da5ade5abc4fe3f.js",
      "2e6413356246f41feb2291856162874f3c697bab71aea97158b92dc107b7ae78",
    ],
    [
      "evidence/web/objects/7128bd47b219d222.js",
      "ffad14f6359d5facd2c363d5b632b7b6f8d42343d0097f3f2ed902f5069f42f0",
    ],
  ]) {
    const f = await corpus.factory(582453, { source });
    assert.equal(f.provenance.sha256, hash);
    const fn = exactlyOne(
      findNodes(
        f.node,
        (n) =>
          n.type === "ArrowFunctionExpression" &&
          n !== f.node &&
          f.text(n).includes('startsWith("0x")'),
      ),
      "used mint normalizer",
    );
    const w = f.witness(fn, "same used582453.f function in both variants");
    assert.equal(
      w.sha256,
      "4e825181227a280ed1b0baf1cb6d2f32af832918dcf6fa05adc52a0697acdc59",
    );
    normalizers.push({ factory: f.provenance, function: w });
  }
  const consumers = [
    { factory: fs[6].provenance, dust: importedCalls(fs[6], 261756, "$") },
    {
      factory: fs[7].provenance,
      dust: importedCalls(fs[7], 261756, "$"),
      spam: importedCalls(fs[7], 947305, "y"),
    },
  ];
  assert.equal(consumers[0].dust.length, 1);
  assert.equal(consumers[1].dust.length, 1);
  assert.equal(consumers[1].spam.length, 1);
  return {
    schemaVersion: 1,
    authority:
      "static read-client recovery; no original bundle execution or backend compatibility",
    anchors: corpus.anchors,
    websiteOrigin: "https://frontend-api-v3.pump.fun",
    developerHostInterchangeable: false,
    dust: {
      operation: "GET /user-portfolio/dust-floor",
      getter: dust.witness(getter, "complete read getter"),
      queryKey: ["userPortfolioDustFloor", "address"],
      addressSent: false,
      credentials: "include",
      signal: "queryFn argument",
      throwHttpErrors: false,
      staleTimeMs: numericProperty(dust, "staleTime"),
      memoSlots: 5,
      positiveNumberOnly: true,
      finiteCheck: false,
      dialogCapAppliedByGetter: false,
      postSetterImplemented: false,
    },
    spam: {
      operation: "GET /user-portfolio/{userId}",
      getter: spam.witness(getterSpam, "complete spam getter"),
      queryKey: ["userPortfolioSpamMints", "address"],
      query: {
        filter: "open",
        spamOnly: true,
        sortBy: "POSITION_SIZE",
        page: 0,
        pageSize: 200,
      },
      credentials: "include",
      signal: "queryFn argument",
      throwHttpErrors: false,
      staleTimeMs: numericProperty(spam, "staleTime"),
      memoSlots: 8,
      mapper:
        "normalize only lowercase0x prefix, Set dedup, native lexicographic sort",
      select: "new Set(array)",
      responseSchemaValidation: false,
    },
    admission: {
      expression: "!!address && enabled",
      defaultsEnabled: false,
      queryRuntimeInjected: true,
      reactMountOrSchedulingQualified: false,
    },
    normalizers,
    consumers,
    factories: fs.map((f) => f.provenance),
    qualifications: {
      nativeBackend: false,
      productionTraffic: false,
      uiIntegrated: false,
      featureCredit: false,
    },
    limits: [
      "Original session ownership/provider/cookies and API behavior remain unknown; cache address is not an authenticated principal.",
      "Private POST setter and all server mutations are excluded. Local add/remove helpers only transform client arrays.",
      "Injected memo/query and single-attempt HTTP ports do not qualify React lifecycle, retries/timeouts or browser auth.",
      "No portfolio valuation, PnL, holdings source, indexer, provider or full SearchDialog/token-page implementation.",
    ],
  };
}
export async function verify(root = APP_ROOT) {
  const fresh = await recover(root);
  // VALIDATION.json pins the contract's sha256, so compare the exact --write bytes.
  assert.equal(
    await readFile(path.join(root, OUTPUT), "utf8"),
    JSON.stringify(fresh, null, 2) + "\n",
    "portfolio policy contract is stale",
  );
  return fresh;
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
    console.log("Original portfolio read-policy source contract PASS");
  } else throw new Error("Use --write or --check");
}
