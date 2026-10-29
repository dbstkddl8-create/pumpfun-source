import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { openCorpus, findNodes, exactlyOne, member, propertyName, objectProperty, literal, sha256 } from './original-contracts/source.mjs';
import { createSchemaExtractor } from './original-contracts/schema.mjs';

export const DEFAULT_APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const CONTRACT_PATH = 'reconstruction/search-client/contract.json';
const SEARCH_CHUNK = 'evidence/web/objects/767cc801e3f88f8b.js';
const RUNTIME_PATH = 'evidence/web/objects/f25d7686d048ae16.js';
const OPERATIONS = ['GET /search/resolve', 'GET /coins/search-v2', 'GET /coins/search-unrestricted'];
const CHAIN_SOURCES = {
  400466: 'evidence/web/objects/13c13db9eb86191b.js',
  544865: 'evidence/web/objects/e02656dccdb8d127.js',
  238128: 'evidence/web/objects/ccb10fa3de5597c4.js',
  759257: 'evidence/web/objects/1e479323ffe53c14.js',
  30181: 'evidence/web/objects/01ad4f413e529b60.js',
  503630: 'evidence/web/objects/1e479323ffe53c14.js',
  402030: 'evidence/web/objects/2b47dd0b38a1608f.js',
  898661: 'evidence/web/objects/2b47dd0b38a1608f.js',
  402734: 'evidence/web/objects/2b47dd0b38a1608f.js',
  985722: 'evidence/web/objects/2b47dd0b38a1608f.js',
};

function expect(condition, label) {
  if (!condition) throw new Error(`unsupported captured search structure: ${label}`);
}

const functionType = (node) => ['FunctionExpression', 'ArrowFunctionExpression', 'FunctionDeclaration'].includes(node?.type);
const tail = (node) => node?.type === 'SequenceExpression' ? node.expressions.at(-1) : node;

function declaration(factory, name) {
  const statements = factory.node.body.body;
  return exactlyOne(statements.flatMap((node) => node.type === 'VariableDeclaration' ? node.declarations : [])
    .filter((node) => node.id.type === 'Identifier' && node.id.name === name), `top-level declaration ${name}`).init;
}

function importBinding(factory, id) {
  const declarations = factory.node.body.body.flatMap((node) => node.type === 'VariableDeclaration' ? node.declarations : []);
  return exactlyOne(declarations.filter((node) => node.id.type === 'Identifier' &&
    node.init?.type === 'CallExpression' &&
    (member(node.init.callee, factory.runtime, 'i') || member(node.init.callee, factory.runtime, 'r')) &&
    node.init.arguments[0]?.value === id), `import binding ${id}`);
}

function exported(factory, name, id = factory.id) {
  const registrations = findNodes(factory.node, (node) => node.type === 'CallExpression' &&
    member(node.callee, factory.runtime, 's') && node.arguments[0]?.type === 'ArrayExpression' &&
    (node.arguments[1] ? node.arguments[1].value === id : factory.ids.length === 1));
  const values = [];
  for (const registration of registrations) {
    const entries = registration.arguments[0].elements;
    for (let i = 0; i < entries.length;) {
      expect(entries[i]?.type === 'StringLiteral', `export name in ${id}`);
      const nameMatches = entries[i].value === name;
      const discriminator = entries[i + 1];
      const value = discriminator?.type === 'NumericLiteral' && discriminator.value === 0 ? entries[i + 2] : discriminator;
      if (nameMatches) values.push(value);
      i += discriminator?.type === 'NumericLiteral' && discriminator.value === 0 ? 3 : 2;
    }
  }
  return exactlyOne(values, `export ${id}.${name}`);
}

function resolveBinding(factory, node) {
  return node.type === 'Identifier' ? declaration(factory, node.name) : node;
}

function routeSchema(factory, operation) {
  const property = exactlyOne(findNodes(factory.node, (node) => node.type === 'ObjectProperty' &&
    node.key.type === 'StringLiteral' && node.key.value === operation), `route declaration ${operation}`);
  const value = property.value.type === 'CallExpression' ? property.value.arguments[1] : property.value;
  expect(value?.type === 'ObjectExpression', `route object ${operation}`);
  return { property, object: value, query: objectProperty(value, 'query'), response: objectProperty(value, 'response') };
}

function operationCall(factory, operation, moduleId, exportName) {
  const binding = importBinding(factory, moduleId);
  return exactlyOne(findNodes(factory.node, (node) => node.type === 'CallExpression' &&
    node.arguments[0]?.type === 'StringLiteral' && node.arguments[0].value === operation &&
    node.callee.type === 'CallExpression' && member(tail(node.callee.callee), binding.id.name, exportName)),
  `client call ${operation}`);
}

async function routeHtml(corpus, route, shell, runtime) {
  const record = exactlyOne(corpus.manifest.records.filter((entry) => entry.status === 200 &&
    new URL(entry.final_url ?? entry.url).pathname === route && /text\/html/i.test(entry.headers?.['content-type'] ?? '')),
  `HTML capture ${route}`);
  const captured = await corpus.capture(record.path);
  const scripts = [...captured.text.matchAll(/<script\b[^>]*\bsrc\s*=\s*(["'])(.*?)\1[^>]*>/gi)]
    .map((match) => new URL(match[2], record.final_url ?? record.url).href);
  expect(scripts.includes(shell.capture.record.url), `${route} shell script`);
  expect(scripts.includes(runtime.record.url), `${route} runtime script`);
  const initialChunks = [];
  const initialCoinHooks = [];
  const unresolvedScripts = [];
  for (const url of scripts) {
    const records = corpus.manifest.records.filter((entry) => entry.status === 200 && entry.url === url);
    if (records.length !== 1 || !new URL(url).pathname.endsWith('.js')) {
      unresolvedScripts.push(url);
      continue;
    }
    const source = await corpus.javascript(records[0].path);
    initialChunks.push({ source: source.record.path, url, sha256: source.record.sha256, bytes: source.record.bytes });
    for (const factory of source.factories) {
      if (factory.ids.includes(379705)) initialCoinHooks.push({ id: 379705, ids: factory.ids,
        ...source.witness(factory.node, `${route} initial coin-hook registration`) });
    }
  }
  return { route, html: { source: record.path, url: record.url, sha256: record.sha256, bytes: record.bytes },
    shellScript: shell.capture.record.url, runtimeScript: runtime.record.url,
    initialChunks, initialCoinHooks, unresolvedScripts };
}

// Recognize this captured loader grammar, not arbitrary JavaScript programs.
export function decodeSearchLoader(factory) {
  const call = exactlyOne(findNodes(factory.node, (node) => node.type === 'CallExpression' &&
    member(node.callee, factory.runtime, 'v')), 'loader value export');
  const loader = call.arguments[0];
  expect(loader?.type === 'ArrowFunctionExpression' && loader.params.length === 1 && loader.params[0].type === 'Identifier', 'loader callback');
  const then = loader.body;
  expect(then.type === 'CallExpression' && then.callee.type === 'MemberExpression' && propertyName(then.callee.property) === 'then', 'loader then');
  // A second then() callback would swallow chunk load failures.
  expect(then.arguments.length === 1, 'loader then without rejection handler');
  const promiseAll = then.callee.object;
  expect(promiseAll.type === 'CallExpression' && member(promiseAll.callee, 'Promise', 'all'), 'loader Promise.all');
  const map = promiseAll.arguments[0];
  expect(map?.type === 'CallExpression' && map.callee.type === 'MemberExpression' &&
    propertyName(map.callee.property) === 'map' && map.callee.object.type === 'ArrayExpression', 'loader chunk map');
  const mapper = map.arguments[0];
  expect(mapper?.type === 'ArrowFunctionExpression' && mapper.params[0]?.type === 'Identifier' &&
    mapper.body.type === 'CallExpression' && member(mapper.body.callee, factory.runtime, 'l') &&
    mapper.body.arguments.length === 1 && mapper.body.arguments[0]?.type === 'Identifier' && mapper.body.arguments[0].name === mapper.params[0].name,
  'loader calls actual runtime.l for each literal');
  const loaded = then.arguments[0];
  expect(loaded?.type === 'ArrowFunctionExpression' && loaded.params.length === 0 &&
    loaded.body.type === 'CallExpression' && loaded.body.callee.type === 'Identifier' &&
    loaded.body.callee.name === loader.params[0].name && loaded.body.arguments.length === 1 &&
    loaded.body.arguments[0].type === 'NumericLiteral', 'loader imported module callback');
  const chunks = map.callee.object.elements.map((node) => {
    expect(node?.type === 'StringLiteral', 'literal loader chunk');
    return node.value;
  });
  return { chunks, targetId: loaded.body.arguments[0].value, node: loader };
}

export async function buildSearchContract(appRoot = DEFAULT_APP_ROOT) {
  const corpus = await openCorpus(appRoot);
  const factories = new Map();
  for (const id of [400466, 544865, 238128, 759257, 30181, 503630, 402030, 898661, 402734, 985722]) {
    factories.set(id, await corpus.factory(id, { source: CHAIN_SOURCES[id] }));
  }
  const shell = factories.get(400466);
  const loader = factories.get(544865);
  const search = factories.get(238128);
  const transport = factories.get(759257);
  const http = factories.get(30181);
  const origin = factories.get(503630);
  const encoder = factories.get(898661);
  const runtime = await corpus.javascript(RUNTIME_PATH);
  const witnesses = [];
  const witness = (factory, node, label) => { const result = factory.witness(node, label); witnesses.push(result); return result; };
  const runtimeAssignment = (name) => exactlyOne(findNodes(runtime.ast, (node) => node.type === 'AssignmentExpression' &&
    member(node.left, 'u', name)), `runtime.${name}`);
  const a = runtimeAssignment('A');
  expect(functionType(a.right) && a.right.params[0]?.name === 'e', 'runtime A callable');
  const aReturn = exactlyOne(a.right.body.body.filter((node) => node.type === 'ReturnStatement'), 'runtime A return').argument;
  expect(aReturn?.type === 'CallExpression' && aReturn.callee.type === 'CallExpression' &&
    aReturn.callee.callee.type === 'MemberExpression' && aReturn.callee.callee.object.type === 'ThisExpression' &&
    propertyName(aReturn.callee.callee.property) === 'r' && aReturn.callee.arguments[0]?.name === 'e' &&
    aReturn.arguments[0]?.type === 'CallExpression' && member(aReturn.arguments[0].callee, 'w', 'bind') &&
    aReturn.arguments[0].arguments[0]?.type === 'ThisExpression', 'runtime A loads exported callback with import binding');
  const v = runtimeAssignment('v');
  expect(v.right.type === 'Identifier', 'runtime value export helper');
  const vHelper = exactlyOne(findNodes(runtime.ast, (node) => node.type === 'FunctionDeclaration' && node.id.name === v.right.name), 'runtime v helper');
  expect(findNodes(vHelper, (node) => node.type === 'AssignmentExpression' && node.left.type === 'MemberExpression' &&
    propertyName(node.left.property) === 'exports').length > 0, 'runtime v assigns module exports');
  const l = exactlyOne(findNodes(runtime.ast, (node) => node.type === 'AssignmentExpression' && member(node.left, '$', 'l')), 'runtime l');
  const loadParent = exactlyOne(findNodes(l.right, (node) => node.type === 'CallExpression' &&
    node.callee.type === 'Identifier' && node.callee.name === 'T'), 'runtime parent loading call');
  expect(member(loadParent.arguments[0], 'o', 'Parent') &&
    loadParent.arguments[1]?.type === 'MemberExpression' && propertyName(loadParent.arguments[1].property) === 'id' &&
    loadParent.arguments[1].object.type === 'MemberExpression' && propertyName(loadParent.arguments[1].object.property) === 'm' &&
    loadParent.arguments[1].object.object.type === 'ThisExpression' &&
    loadParent.arguments[2]?.name === l.right.params[0]?.name, 'runtime l delegates to parent chunk loading');
  for (const [node, label] of [[a, 'runtime.A callback invocation'], [vHelper, 'runtime.v module export'], [l, 'runtime.l chunk loading']]) {
    witnesses.push(runtime.witness(node, label));
  }
  const registrationDecoder = exactlyOne(findNodes(runtime.ast, (node) => node.type === 'FunctionDeclaration' && node.id.name === 'X'), 'runtime registration decoder');
  witnesses.push(runtime.witness(registrationDecoder, 'global factory map preserves already registered IDs'));
  for (const cacheRead of findNodes(runtime.ast, (node) => node.type === 'CallExpression' && member(node.callee, 'D', 'get'))) {
    witnesses.push(runtime.witness(cacheRead, 'runtime module cache lookup'));
  }
  const shellLoad = exactlyOne(findNodes(shell.node, (node) => node.type === 'CallExpression' &&
    member(node.callee, shell.runtime, 'A') && node.arguments[0]?.value === 544865), 'shell dynamic search loader');
  witness(shell, shellLoad, 'shell requests loader 544865');
  const decoded = decodeSearchLoader(loader);
  expect(decoded.targetId === search.id, 'loader selects SearchDialogLazy');
  witness(loader, decoded.node, 'literal search chunk closure');
  const chunks = [];
  const contextualHooks = [];
  for (const relative of decoded.chunks) {
    const url = new URL(relative, 'https://pump.fun/_next/').href;
    const record = exactlyOne(corpus.manifest.records.filter((entry) => entry.status === 200 && entry.url === url), `loader chunk ${relative}`);
    const captured = await corpus.javascript(record.path);
    for (const factory of captured.factories) {
      if (factory.ids.includes(379705)) contextualHooks.push({ source: record.path, node: factory.node });
    }
    chunks.push({ path: record.path, url, sha256: record.sha256, bytes: record.bytes });
  }
  const loadedPaths = new Set(chunks.map((chunk) => chunk.path));
  expect(loadedPaths.has(search.capture.record.path), 'search target in actual loader chunk list');
  expect(contextualHooks.length === 1 && contextualHooks[0].source === SEARCH_CHUNK, 'unambiguous loader-context coin hook');
  const coinHook = await corpus.factory(379705, { source: contextualHooks[0].source });
  factories.set(379705, coinHook);
  const routes = await Promise.all(['/', '/explore'].map((route) => routeHtml(corpus, route, shell, runtime)));
  const physicalHookVariants = new Map([[coinHook.provenance.sha256, coinHook]]);
  for (const route of routes) {
    for (const candidate of route.initialCoinHooks) {
      const factory = await corpus.factory(379705, { source: candidate.source });
      physicalHookVariants.set(candidate.sha256, factory);
    }
    route.coinHookCandidates = [...route.initialCoinHooks, coinHook.provenance];
    route.selection = 'Conditional static candidates only. Initial scripts and lazy chunks share the runtime registration map/cache; this report does not choose an active variant or establish execution order.';
  }
  witness(search, importBinding(search, 379705), 'dialog imports contextual coin hook');
  const resolverCall = operationCall(search, OPERATIONS[0], 759257, 'j');
  const query = objectProperty(resolverCall.arguments[1], 'query');
  expect(query.type === 'ObjectExpression' && objectProperty(query, 'identifiers').type === 'ArrayExpression' &&
    objectProperty(query, 'identifiers').elements.length === 1, 'resolver sends one identifier');
  witness(search, resolverCall, 'resolver GET query and abort signal');
  const resolver = declaration(search, 'e4');
  witness(search, resolver, 'resolver catches errors and branches on definitive/kind/mint/chain');
  for (const name of ['j', 'f']) {
    const exportedClient = exported(transport, name);
    witness(transport, exportedClient, `website transport export ${name}`);
    expect(functionType(exportedClient), `transport ${name} function`);
    const client = exactlyOne(findNodes(exportedClient, (node) => node.type === 'CallExpression' &&
      member(tail(node.callee), importBinding(transport, 30181).id.name, 'K')), `transport ${name} contract-client call`);
    const base = objectProperty(client.arguments[0], 'clientServerUrl');
    const baseCall = name === 'j' ? base : base.alternate;
    expect(baseCall?.type === 'CallExpression' && member(tail(baseCall.callee), importBinding(transport, 503630).id.name, 'R'),
      `transport ${name} origin export R`);
    if (name === 'f') {
      expect(base.type === 'ConditionalExpression' && base.test.type === 'CallExpression' && base.test.callee.type === 'Identifier' &&
        literal(declaration(transport, base.test.callee.name).body) === false &&
        base.consequent.type === 'StringLiteral' && base.consequent.value === '/api/client-server', 'captured proxy flag is false');
    }
  }
  witness(transport, declaration(transport, 's'), 'website default credentials');
  const defaultCredentials = literal(objectProperty(declaration(transport, 's'), 'credentials'));
  expect(defaultCredentials === 'same-origin', 'website credentials override');
  const originFn = resolveBinding(origin, exported(origin, 'R'));
  expect(functionType(originFn) && originFn.body.type === 'StringLiteral', 'literal client origin function');
  const websiteOrigin = originFn.body.value;
  witness(origin, originFn, 'website client server origin');
  witness(http, exported(http, 'K'), 'contract-client constructor');
  const bridge = factories.get(402030);
  const bridgeImport = importBinding(bridge, 898661);
  const getter = exactlyOne(findNodes(bridge.node, (node) => node.type === 'CallExpression' &&
    member(node.callee, 'Object', 'defineProperty') && node.arguments[1]?.value === 'createContractClient'), 'contract-client reexport');
  const getterBody = exactlyOne(findNodes(getter.arguments[2], (node) => node.type === 'ReturnStatement'), 'contract-client getter return');
  expect(member(getterBody.argument, bridgeImport.id.name, 'createContractClient'), 'contract-client reexport target');
  witness(bridge, getter, 'contract-client reexport to factory898661');
  witness(http, declaration(http, '_'), 'HTTP client prefix and default hooks');
  const headersNode = declaration(http, '$');
  const headers = Object.fromEntries(headersNode.properties.map((entry) => [propertyName(entry.key), literal(entry.value)]));
  witness(http, headersNode, 'default WEB/web request headers');
  const jsonAccept = literal(objectProperty(declaration(http, 'h'), 'json'));
  const acceptSetter = exactlyOne(findNodes(http.node, (node) => node.type === 'CallExpression' &&
    node.callee.type === 'MemberExpression' && propertyName(node.callee.property) === 'set' &&
    node.arguments[0]?.type === 'StringLiteral' && node.arguments[0].value === 'accept'), 'JSON reader Accept header');
  witness(http, acceptSetter, 'response reader defaults Accept to application/json');
  headers.Accept = jsonAccept;
  witness(encoder, exactlyOne(findNodes(encoder.node, (node) => node.type === 'AssignmentExpression' &&
    node.left.type === 'MemberExpression' && propertyName(node.left.property) === 'createContractClient' &&
    functionType(node.right)), 'contract encoder definition'),
  'query encoding, route interpolation, response JSON and error wrapping');
  const coinRequestContexts = [];
  for (const candidate of physicalHookVariants.values()) {
    const searchCallback = exactlyOne(findNodes(candidate.node, (node) =>
      node.type === 'ArrowFunctionExpression' && node.async && findNodes(node, (child) =>
        child.type === 'ObjectProperty' && propertyName(child.key) === 'route' && child.value.value === 'GET /coins/search-v2').length === 1),
    'coin search callback');
    for (const operation of OPERATIONS.slice(1)) {
      witness(candidate, exactlyOne(findNodes(searchCallback, (node) => node.type === 'ObjectProperty' &&
        propertyName(node.key) === 'route' && node.value.type === 'StringLiteral' && node.value.value === operation),
      `coin search route ${operation}`), `${operation} in ${candidate.provenance.sha256}`);
    }
    const queryCall = exactlyOne(findNodes(searchCallback, (node) => node.type === 'CallExpression' &&
      node.callee.type === 'Identifier' && node.arguments[0]?.type === 'ObjectExpression' &&
      node.arguments[0].properties.some((property) => propertyName(property.key) === 'useLocalFilterLimit')), 'query-builder call');
    const queryBuilder = exactlyOne(findNodes(candidate.node, (node) => node.type === 'VariableDeclarator' &&
      node.id.type === 'Identifier' && node.id.name === queryCall.callee.name), 'query-builder declaration').init;
    witness(candidate, queryBuilder, 'conditional coin query-builder context');
    const imported = importBinding(candidate, 759257);
    const call = exactlyOne(findNodes(candidate.node, (node) => node.type === 'CallExpression' &&
      node.callee.type === 'CallExpression' && member(tail(node.callee.callee), imported.id.name, 'f')), 'coin client request');
    const credentials = literal(objectProperty(call.arguments[1], 'credentials'));
    const contentType = literal(objectProperty(objectProperty(call.arguments[1], 'headers'), 'Content-Type'));
    expect(credentials === 'include' && contentType === 'application/json', 'reviewed common coin request options');
    witness(candidate, call, 'conditional coin request options');
    coinRequestContexts.push({ factory: candidate.provenance, operations: OPERATIONS.slice(1), credentials, contentType,
      queryPlanning: 'Source-bound per-variant witness; complete query-builder equivalence and active runtime selection are not claimed' });
  }
  const schemas = await createSchemaExtractor(corpus, { sources: {
    402734: CHAIN_SOURCES[402734], 985722: CHAIN_SOURCES[985722],
    876543: 'evidence/web/objects/2b47dd0b38a1608f.js',
    599565: 'evidence/web/objects/06e532443c8db686.js',
    408162: 'evidence/web/objects/d50c5c8832449b79.js',
  } });
  const operations = {};
  const querySchemas = {};
  for (const operation of OPERATIONS) {
    const factory = factories.get(operation === OPERATIONS[0] ? 402734 : 985722);
    const schema = routeSchema(factory, operation);
    const requestSchema = await schemas.compile(schema.query, factory);
    querySchemas[operation] = requestSchema;
    witness(factory, schema.query, `${operation} declared query schema`);
    witness(factory, schema.response, `${operation} declared response schema`);
    operations[operation] = { method: 'GET', path: operation.slice(4), websiteOrigin,
      credentials: operation === OPERATIONS[0] ? defaultCredentials : 'include', headers,
      querySchemaPointer: `#/properties/${operation.replaceAll('~', '~0').replaceAll('/', '~1')}`,
      queryEncoding: { undefined: 'omitted', scalar: 'String(value)', array: 'String(item), reject commas, join with comma',
        emptyArray: 'omit only when the named query field accepts undefined; otherwise throw TypeError',
        validation: 'the client does not parse nonempty query values with the declared query schema' },
      responseHandling: operation === OPERATIONS[0] ? {
        input: 'JSON results[0]', errorOrMissingOrNotDefinitive: { kind: 'fallback' },
        coin: 'truthy coin.mint -> {kind:coin,mint,chain:chain ?? null}; otherwise fallback',
        user: { kind: 'user' }, external_wallet: { kind: 'external_wallet' },
        squadAndUnknown: { kind: 'fallback' }, degraded: 'not consumed by this resolver helper',
      } : { input: 'JSON response', furtherHookBehavior: 'coin normalization, chain filtering, stale-response guards and pagination remain outside the small adapter' },
      qualification: 'static captured client contract; no upstream behavior qualification' };
  }
  const allFactories = [...factories.values(), ...[...physicalHookVariants.values()].filter((candidate) => candidate !== coinHook)];
  const selectedHashes = new Set([...allFactories.map((factory) => factory.provenance.sha256),
    ...schemas.witnesses().filter((record) => /^factory \d+$/.test(record.label)).map((record) => record.sha256)]);
  const selectedEntries = corpus.index.modules.filter((entry) => selectedHashes.has(entry.sha256))
    .sort((left, right) => left.sha256.localeCompare(right.sha256));
  expect(selectedEntries.length === selectedHashes.size, 'one complete index entry per selected factory hash');
  return { schemaVersion: 1,
    source: { repository: 'lalalune/pumpfun-source', base: '2fc654a20e9c7be2b9529f585942bb82c4c83ab2',
      manifestSha256: corpus.anchors.manifestSha256,
      inventorySelectionSha256: sha256(JSON.stringify(selectedEntries)) },
    inventory: { selectedEntries,
      completeness: 'Not claimed. The inventory supplies bounded source references; initial and lazy physical chunks are independently parsed, including leading nested registrations.' },
    scope: 'Captured shared search loader, client request contract, resolver handling and declared query schemas; original TypeScript and backend implementation remain unknown',
    routes,
    loader: { id: loader.id, targetId: decoded.targetId, chunks,
      registrationPolicy: 'The captured global factory map preserves existing IDs and module caches can predate lazy loading. No active registration/cache state is captured.',
      chunkUrlResolution: 'Literal _next-relative chunk names matched to retained authenticated pump.fun asset URLs; runtime global base-path overrides are not executed or qualified',
      lazyCoinHookCandidate: coinHook.provenance },
    factories: allFactories.map((factory) => factory.provenance).sort((a, b) => a.id - b.id),
    coinRequestContexts,
    operations,
    querySchemas: schemas.document({ type: 'object', properties: querySchemas }),
    witnesses: [...witnesses, ...schemas.witnesses()].sort((a, b) => a.source.localeCompare(b.source) || a.utf16[0] - b.utf16[0] || a.label.localeCompare(b.label)),
    limits: ['No captured JavaScript is evaluated.', 'Chunk provenance demonstrates a static loading chain, not execution or complete route reachability.',
      'The small adapter does not reproduce Ky retries, ContractError wrapping, cache behavior, coin normalization, full hook lifecycle, backend responses or auth enforcement.',
      'The captured website origin and cookie options do not establish that the developer API origin uses the same authentication.',
      'No API, feature-progress or live compatibility milestone is awarded.'] };
}

export async function verifySearchContract(appRoot = DEFAULT_APP_ROOT) {
  const expected = JSON.stringify(await buildSearchContract(appRoot), null, 2) + '\n';
  const actual = await readFile(path.join(appRoot, CONTRACT_PATH), 'utf8');
  if (actual !== expected) throw new Error('search contract differs from authenticated captured source; regenerate and review');
  return JSON.parse(actual);
}

export async function compareSearchInventory(otherPath, appRoot = DEFAULT_APP_ROOT) {
  const contract = await buildSearchContract(appRoot);
  const corpus = await openCorpus(appRoot);
  const otherBytes = await readFile(otherPath);
  const other = JSON.parse(otherBytes);
  expect(other.rangeEncoding === corpus.index.rangeEncoding && Array.isArray(other.modules), 'comparable inventory format');
  const hashes = new Set(contract.inventory.selectedEntries.map((entry) => entry.sha256));
  const selection = other.modules.filter((entry) => hashes.has(entry.sha256)).sort((a, b) => a.sha256.localeCompare(b.sha256));
  expect(JSON.stringify(selection) === JSON.stringify(contract.inventory.selectedEntries), 'complete selected index entries differ');
  return { schemaVersion: 1, equalCompleteSelectedEntries: true, selectedEntries: selection.length,
    selectionSha256: contract.source.inventorySelectionSha256,
    maintainedIndex: { sha256: corpus.anchors.inventorySha256, variants: corpus.index.modules.length,
      origins: corpus.index.modules.reduce((total, entry) => total + entry.origins.length, 0) },
    comparedIndex: { sha256: sha256(otherBytes), variants: other.modules.length,
      origins: other.modules.reduce((total, entry) => total + entry.origins.length, 0) },
    scope: 'Exact complete-entry equality for this bounded selection only; no inventory completeness or runtime selection claim' };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const [mode, ...rest] = process.argv.slice(2);
    if (mode === '--compare-index' && rest.length === 1) {
      console.log(JSON.stringify(await compareSearchInventory(rest[0]), null, 2));
    } else {
      if (!['--write', '--check'].includes(mode) || rest.length) throw new Error('usage: node scripts/original-search-contract.mjs --write|--check|--compare-index <index.json>');
      if (mode === '--write') {
        const contract = await buildSearchContract();
        await mkdir(path.dirname(path.join(DEFAULT_APP_ROOT, CONTRACT_PATH)), { recursive: true });
        await writeFile(path.join(DEFAULT_APP_ROOT, CONTRACT_PATH), JSON.stringify(contract, null, 2) + '\n');
      } else await verifySearchContract();
      console.log(`Original search contract ${mode === '--write' ? 'written' : 'verified'}: 3 GET operations; captured JavaScript was not executed.`);
    }
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
