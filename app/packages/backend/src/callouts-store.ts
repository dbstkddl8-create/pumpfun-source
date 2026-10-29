/** Server-owned public callout materialization; not a price, ranking, or identity service. */
import {
  closeSync,
  constants,
  fstatSync,
  openSync,
  readFileSync,
  readSync,
} from "node:fs";
import {
  CalloutListError,
  decodeCalloutPage,
  encodeCalloutPage,
  fingerprint,
  parseCalloutListQuery,
} from "./callout-list-query.js";
import type { operations, components } from "./generated/developer-api.js";
import { assertSchema, type SchemaNode } from "./schema-validator.js";

export type Callout = NonNullable<
  operations["get_callout_by_calloutId"]["responses"][200]["content"]["application/json"]["callout"]
>;
export type UserMintCalloutResponse =
  operations["get_callout_user_by_userId_mint_by_coinMint"]["responses"][200]["content"]["application/json"];
/** Missing local facts/policy, not a reconstructed production error. */
export class CalloutLookupError extends Error {}
export type QuotedCallout = components["schemas"]["Shared_85bd3a13acc3"];
export type CalloutListResponse =
  operations["get_callout_list_by_userId"]["responses"][200]["content"]["application/json"];
export type CalloutListItem = CalloutListResponse["callouts"][number];
const tailFields = [
  "tailBuyers",
  "tailCohort1h",
  "tailPnl1hUsd",
  "tailCohort4h",
  "tailPnl4hUsd",
  "tailCohort24h",
  "tailPnl24hUsd",
  "tailPnlHist1h",
  "tailPnlHist4h",
  "tailPnlHist24h",
  "tailAth1hUsd",
  "tailAth4hUsd",
  "tailAth24hUsd",
  "tailAthHist1h",
  "tailAthHist4h",
  "tailAthHist24h",
] as const;
export type CalloutTailFacts = Partial<
  Pick<CalloutListItem, (typeof tailFields)[number]>
>;
export type CalloutUpdate = Callout["updates"][number];
const authorFields = [
  "userName",
  "profileImage",
  "isVerified",
  "verifiedBadgeVisible",
  "accountKind",
  "xUsername",
  "xFollowerCount",
] as const;
type AuthorFields = (typeof authorFields)[number];
export type CalloutAuthor = Pick<Callout, AuthorFields> & { authorId: string };
export type CalloutFacts = Omit<
  Callout,
  | AuthorFields
  | "user_uuid"
  | "updates"
  | "quotedCallout"
  | "hasLiked"
  | "hasReposted"
>;
/** A separate wire projection: USD/market-cap fields are supplied, never converted from SOL here. */
export type QuoteFacts = Omit<
  QuotedCallout["callout"],
  "updates" | "quotedCallout" | "hasLiked" | "hasReposted"
>;
export interface CalloutsDataset {
  schemaVersion: 1;
  dataSource: "synthetic" | "local-materialized";
  observedAt: string;
  authors: CalloutAuthor[];
  callouts: Array<{
    calloutId: string;
    authorId: string;
    hidden: boolean;
    deleted: boolean;
    /** Null records explicitly represent a row not mappable to the legacy shape. */
    facts: CalloutFacts | null;
    /** Optional separately materialized one-level quote projection. */
    quoteFacts?: QuoteFacts;
    /** Optional list-only measurements. Omitted fields remain unknown (null), never computed. */
    tailFacts?: CalloutTailFacts;
  }>;
  updates: Array<{
    calloutId: string;
    authorId: string;
    hidden: boolean;
    deleted: boolean;
    body: CalloutUpdate;
  }>;
}
const spec = JSON.parse(
  readFileSync(
    new URL("../../../contracts/developer.openapi.json", import.meta.url),
    "utf8",
  ),
);
const responseSchema: SchemaNode =
  spec.paths["/callout/{calloutId}"].get.responses[200].content[
    "application/json"
  ].schema;
const listItemSchema: SchemaNode =
  spec.paths["/callout/list/{userId}"].get.responses[200].content[
    "application/json"
  ].schema.properties.callouts.items;
const tailFactsSchema: SchemaNode = {
  type: "object",
  additionalProperties: false,
  properties: Object.fromEntries(
    tailFields.map((key) => [key, listItemSchema.properties![key]]),
  ),
};
const unknownTailFacts = Object.fromEntries(
  tailFields.map((key) => [key, null]),
) as Pick<CalloutListItem, (typeof tailFields)[number]>;
const calloutSchema = responseSchema.properties!.callout;
const quoteSchema: SchemaNode = spec.components.schemas.Shared_85bd3a13acc3;
const quoteInnerSchema = quoteSchema.properties!.callout;
function without(schema: SchemaNode, excluded: readonly string[]): SchemaNode {
  return {
    ...schema,
    nullable: false,
    properties: Object.fromEntries(
      Object.entries(schema.properties!).filter(
        ([key]) => !excluded.includes(key),
      ),
    ),
    required: schema.required!.filter((key) => !excluded.includes(key)),
  };
}
const factsSchema = without(calloutSchema, [
  ...authorFields,
  "user_uuid",
  "updates",
  "quotedCallout",
  "hasLiked",
  "hasReposted",
]);
const quoteFactsSchema = without(quoteInnerSchema, [
  "updates",
  "quotedCallout",
  "hasLiked",
  "hasReposted",
]);
const authorSchema: SchemaNode = {
  type: "object",
  additionalProperties: false,
  properties: {
    authorId: { type: "string", minLength: 1 },
    ...Object.fromEntries(
      authorFields.map((key) => [key, calloutSchema.properties![key]]),
    ),
  },
  required: ["authorId", ...authorFields],
};
function fail(message: string): never {
  throw new Error(`Invalid callouts materialization: ${message}`);
}
function object(
  value: unknown,
  keys: readonly string[],
  label: string,
): asserts value is Record<string, unknown> {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.getPrototypeOf(value) !== Object.prototype
  )
    fail(`${label} must be a plain JSON object`);
  if (Object.keys(value).some((key) => !keys.includes(key)))
    fail(`${label} has unsupported fields`);
}
function identity(value: unknown, label: string): asserts value is string {
  if (typeof value !== "string" || !value || /[\x00-\x1f\x7f]/.test(value))
    fail(`${label} must be nonempty text`);
}
function instant(value: unknown, label: string): void {
  if (
    typeof value !== "string" ||
    !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$/.test(value) ||
    !Number.isFinite(Date.parse(value))
  )
    fail(`${label} must be a UTC ISO instant`);
  const canonical = value.replace(
    /(?:\.(\d{1,3}))?Z$/,
    (_, fraction: string | undefined) => `.${(fraction ?? "").padEnd(3, "0")}Z`,
  );
  if (new Date(value).toISOString() !== canonical)
    fail(`${label} has an invalid calendar date`);
}
export function assertCalloutJson(value: unknown, depth = 0): void {
  if (depth > 30) fail("nested input exceeds the local limit");
  if (
    value === null ||
    typeof value === "boolean" ||
    typeof value === "string" ||
    (typeof value === "number" && Number.isFinite(value))
  )
    return;
  if (Array.isArray(value)) {
    if (Reflect.ownKeys(value).length !== value.length + 1)
      fail("arrays must be dense JSON lists");
    for (let index = 0; index < value.length; index++) {
      const descriptor = Object.getOwnPropertyDescriptor(value, index);
      if (!descriptor || !Object.hasOwn(descriptor, "value"))
        fail("unsupported array field");
      assertCalloutJson(descriptor.value, depth + 1);
    }
    return;
  }
  if (
    !value ||
    typeof value !== "object" ||
    Object.getPrototypeOf(value) !== Object.prototype
  )
    fail("input must contain finite plain JSON only");
  if (Object.getOwnPropertySymbols(value).length)
    fail("symbol fields are not JSON");
  for (const [key, descriptor] of Object.entries(
    Object.getOwnPropertyDescriptors(value),
  )) {
    if (
      key === "prototype" ||
      Object.hasOwn(Object.prototype, key) ||
      !Object.hasOwn(descriptor, "value") ||
      !descriptor.enumerable
    )
      fail("unsupported object field");
    assertCalloutJson(descriptor.value, depth + 1);
  }
}
const counters = new Set([
  "likes",
  "likeCount",
  "updateCount",
  "commentCount",
  "replyCount",
  "quoteCount",
  "repostCount",
  "viewCount",
  "xFollowerCount",
]);
const spotChain = /^(solana:[A-Za-z0-9]{1,48}|eip155:[1-9]\d{0,47})$/;
/** Local admission is intentionally narrower than the complete multi-asset OpenAPI DTO. */
function publicSpot(value: unknown): void {
  if (!value || typeof value !== "object") return;
  for (const [key, child] of Object.entries(value)) {
    if ((key === "hasLiked" || key === "hasReposted") && child !== null)
      fail("viewer-specific state is not public");
    if ((key === "perp" || key === "collectible") && child !== null)
      fail("only spot-token callouts are supported");
    if (key === "assetClass" && child !== "ASSET_CLASS_TOKEN")
      fail("only spot-token callouts are supported");
    if (
      key === "chain" &&
      child !== null &&
      (typeof child !== "string" || !spotChain.test(child))
    )
      fail("unsupported chain");
    if (
      counters.has(key) &&
      (!Number.isSafeInteger(child) || (child as number) < 0)
    )
      fail("counters must be nonnegative safe integers");
    if (["calloutTimestamp", "maxMultiplierAt"].includes(key) && child !== null)
      instant(child, key);
    if (key === "createdAt" && child !== null) {
      if (typeof child === "number") {
        if (!Number.isSafeInteger(child) || child < 0)
          fail("createdAt must be epoch milliseconds");
      } else instant(child, key);
    }
    publicSpot(child);
  }
}
function visibility(row: { hidden: unknown; deleted: unknown }): void {
  if (typeof row.hidden !== "boolean" || typeof row.deleted !== "boolean")
    fail("visibility must be explicit");
}
const orderText = (a: string, b: string) => (a === b ? 0 : a < b ? -1 : 1);

export class CalloutsStore {
  readonly dataSource: CalloutsDataset["dataSource"];
  readonly observedAt: string;
  private readonly authors = new Map<string, CalloutAuthor>();
  private readonly callouts = new Map<
    string,
    CalloutsDataset["callouts"][number]
  >();
  private readonly snapshot: string;
  private readonly updates = new Map<string, CalloutUpdate[]>();

  constructor(input: unknown) {
    assertCalloutJson(input);
    object(
      input,
      [
        "schemaVersion",
        "dataSource",
        "observedAt",
        "authors",
        "callouts",
        "updates",
      ],
      "dataset",
    );
    if (
      input.schemaVersion !== 1 ||
      !["synthetic", "local-materialized"].includes(input.dataSource as string)
    )
      fail("schemaVersion/dataSource");
    instant(input.observedAt, "observedAt");
    for (const key of ["authors", "callouts", "updates"])
      if (!Array.isArray(input[key])) fail(`${key} must be an array`);
    const data = structuredClone(input) as unknown as CalloutsDataset;
    this.dataSource = data.dataSource;
    this.observedAt = data.observedAt;
    for (const author of data.authors) {
      assertSchema(author, authorSchema, "author", spec);
      identity(author.authorId, "authorId");
      publicSpot(author);
      if (this.authors.has(author.authorId)) fail("duplicate author identity");
      this.authors.set(author.authorId, author);
    }
    for (const row of data.callouts) {
      object(
        row,
        [
          "calloutId",
          "authorId",
          "hidden",
          "deleted",
          "facts",
          "quoteFacts",
          "tailFacts",
        ],
        "callout",
      );
      identity(row.calloutId, "calloutId");
      identity(row.authorId, "authorId");
      visibility(row);
      if (this.callouts.has(row.calloutId)) fail("duplicate callout identity");
      if (!this.authors.has(row.authorId)) fail("unresolved author identity");
      if (row.facts !== null) {
        assertSchema(row.facts, factsSchema, "callout facts", spec);
        publicSpot(row.facts);
        if (row.facts.createdAt !== null && row.facts.createdAt > Date.parse(this.observedAt)) fail("callout timestamp exceeds observedAt");
        if (row.facts.maxMultiplierAt != null && Date.parse(row.facts.maxMultiplierAt) > Date.parse(this.observedAt)) fail("callout maxMultiplierAt exceeds observedAt");
        if (row.facts.calloutId !== row.calloutId)
          fail("callout identity mismatch");
        identity(row.facts.userId, "posting wallet");
        identity(row.facts.coinMint, "coinMint");
        if (row.facts.coinMint.startsWith("hlcore:"))
          fail("perpetual coin references are not supported");
        if (row.facts.quotedCalloutId !== null)
          identity(row.facts.quotedCalloutId, "quotedCalloutId");
      }
      if (row.quoteFacts !== undefined) {
        assertSchema(row.quoteFacts, quoteFactsSchema, "quote facts", spec);
        publicSpot(row.quoteFacts);
        for (const at of [row.quoteFacts.calloutTimestamp, row.quoteFacts.maxMultiplierAt])
          if (at != null && Date.parse(at) > Date.parse(this.observedAt)) fail("quote timestamp exceeds observedAt");
        if (!row.facts || row.quoteFacts.calloutId !== row.calloutId)
          fail("quote projection identity mismatch");
        if (
          (row.quoteFacts.quotedCalloutId ?? null) !== row.facts.quotedCalloutId
        )
          fail("quote target identity mismatch");
        if ((row.quoteFacts.chain ?? null) !== (row.facts.chain ?? null))
          fail("quote chain mismatch");
        if (
          row.quoteFacts.actingUser &&
          row.quoteFacts.actingUser.userId !== row.quoteFacts.actingUserId
        )
          fail("acting identity mismatch");
      }
      if (row.tailFacts !== undefined) {
        assertSchema(row.tailFacts, tailFactsSchema, "tail facts", spec);
        // Counts and ATH totals have nonnegative semantics; PnL can legitimately be negative.
        const checkCounts = (value: unknown): void => {
          if (!value || typeof value !== "object") return;
          for (const [key, child] of Object.entries(value)) {
            if (
              child !== null &&
              (["tailBuyers", "tailers", "callouts"].includes(key) ||
                key.startsWith("tailCohort"))
            ) {
              if (!Number.isSafeInteger(child) || (child as number) < 0)
                fail("tail counts must be nonnegative safe integers");
            }
            if (
              /^tailAth\d+hUsd$/.test(key) &&
              child !== null &&
              (child as number) < 0
            )
              fail("tail ATH totals must be nonnegative");
            checkCounts(child);
          }
        };
        checkCounts(row.tailFacts);
      }
      this.callouts.set(row.calloutId, row);
    }
    const updateIds = new Set<string>();
    for (const row of data.updates) {
      object(
        row,
        ["calloutId", "authorId", "hidden", "deleted", "body"],
        "update",
      );
      identity(row.calloutId, "update.calloutId");
      identity(row.authorId, "update.authorId");
      visibility(row);
      assertSchema(
        row.body,
        calloutSchema.properties!.updates.items!,
        "update",
        spec,
      );
      publicSpot(row.body);
      if (row.body.createdAt !== null && Date.parse(row.body.createdAt) > Date.parse(this.observedAt)) fail("update timestamp exceeds observedAt");
      identity(row.body.id, "update.id");
      if (updateIds.has(row.body.id)) fail("duplicate update identity");
      updateIds.add(row.body.id);
      const callout = this.callouts.get(row.calloutId);
      if (!callout) fail("update references missing callout");
      // Non-author replies and moderation-hidden rows never enter the public update relation.
      if (row.authorId !== callout.authorId || row.hidden || row.deleted)
        continue;
      const rows = this.updates.get(row.calloutId) ?? [];
      rows.push(row.body);
      this.updates.set(row.calloutId, rows);
    }
    for (const rows of this.updates.values())
      rows.sort((a, b) => {
        const at = a.createdAt === null ? -Infinity : Date.parse(a.createdAt);
        const bt = b.createdAt === null ? -Infinity : Date.parse(b.createdAt);
        return (at === bt ? 0 : at > bt ? -1 : 1) || orderText(b.id, a.id);
      });
    this.snapshot = fingerprint(data);
  }

  get(calloutId: string): { callout: Callout | null } {
    const row = this.live(calloutId);
    if (!row || !row.facts) return { callout: null };
    const { authorId, ...author } = this.authors.get(row.authorId)!;
    const result: Callout = {
      ...row.facts,
      ...author,
      user_uuid: authorId,
      hasLiked: null,
      hasReposted: null,
      updates: this.updates.get(calloutId) ?? [],
      quotedCallout: row.facts.quotedCalloutId
        ? this.quote(row.facts.quotedCalloutId)
        : null,
    };
    // Caller mutation cannot alter subsequent reads, including nested author/update/quote objects.
    return structuredClone({ callout: result });
  }
  /** An unambiguous live slot in the supplied local materialization only. */
  getByUserMint(userId: string, coinMint: string): UserMintCalloutResponse {
    if (!this.authors.has(userId))
      throw new CalloutLookupError("CALLOUT_LOOKUP_UNKNOWN");
    const live = [...this.callouts.values()].filter(
      (row) => row.authorId === userId && !row.hidden && !row.deleted,
    );
    // An unmapped row could occupy this mint; its missing identity is not absence.
    if (live.some((row) => row.facts === null))
      throw new CalloutLookupError("CALLOUT_LOOKUP_UNMAPPED");
    const matches = live.filter((row) => row.facts!.coinMint === coinMint);
    if (matches.length > 1)
      throw new CalloutLookupError("CALLOUT_LOOKUP_AMBIGUOUS");
    if (!matches.length) return { callout: null, quotes: [] };
    if (matches[0].facts!.chain != null)
      throw new CalloutLookupError("CALLOUT_LOOKUP_CHAIN_UNAVAILABLE");
    const {
      userName,
      profileImage,
      isVerified,
      verifiedBadgeVisible,
      accountKind,
      xUsername,
      xFollowerCount,
      ...callout
    } = this.get(matches[0].calloutId).callout!;
    return { callout, quotes: [] };
  }
  /** Single-author full-history slice of this local public materialization only. */
  list(userId: string, query = new URLSearchParams()): CalloutListResponse {
    const { pageToken, ...options } = parseCalloutListQuery(query);
    const author = this.authors.get(userId);
    if (!author)
      throw new CalloutListError(501, "CALLOUT_LIST_AUTHOR_UNAVAILABLE");
    if (options.includeMembers && author.accountKind === "group")
      throw new CalloutListError(501, "CALLOUT_LIST_MEMBERS_UNAVAILABLE");
    const rows = [...this.callouts.values()].filter(
      (row) =>
        row.authorId === userId && !row.hidden && !row.deleted && row.facts,
    );
    const field = options.sortBy === "TIMESTAMP" ? "createdAt" : "multiple";
    const direction = options.sortOrder === "ASC" ? 1 : -1;
    // Numeric fact ordering and code-unit ID ties are local policy, not upstream ranking.
    rows.sort((a, b) => {
      const av = a.facts![field],
        bv = b.facts![field];
      return (
        direction *
        ((av === bv ? 0 : av < bv ? -1 : 1) ||
          orderText(a.calloutId, b.calloutId))
      );
    });
    const scope = fingerprint([userId, options]);
    const offset = decodeCalloutPage(
      pageToken,
      this.snapshot,
      scope,
      options.limit,
      rows.length,
    );
    const end = Math.min(rows.length, offset + options.limit);
    const callouts = rows.slice(offset, end).map(
      (row): CalloutListItem => ({
        ...row.facts!,
        user_uuid: "",
        hasLiked: null,
        hasReposted: null,
        updates: this.updates.get(row.calloutId) ?? [],
        quotedCallout: row.facts!.quotedCalloutId
          ? this.quote(row.facts!.quotedCalloutId)
          : null,
        ...unknownTailFacts,
        ...row.tailFacts,
        ...(author.userName !== null
          ? {
              author: {
                userId: author.authorId,
                userName: author.userName,
                profileImage: author.profileImage,
                accountKind: author.accountKind,
              },
            }
          : {}),
      }),
    );
    return structuredClone({
      callouts,
      nextPageToken:
        end < rows.length ? encodeCalloutPage(this.snapshot, scope, end) : "",
    });
  }
  private live(id: string) {
    const row = this.callouts.get(id);
    return row && !row.hidden && !row.deleted && row.facts ? row : null;
  }
  private quote(id: string): QuotedCallout | null {
    const row = this.live(id);
    if (!row?.quoteFacts || !row.facts) return null;
    const { authorId, ...author } = this.authors.get(row.authorId)!;
    return {
      ...author,
      userId: authorId,
      walletAddress: row.facts.userId,
      coinMint: row.facts.coinMint,
      mediaUrl: row.quoteFacts.mediaUrl,
      ...(row.facts.chain != null ? { chain: row.facts.chain } : {}),
      ...(row.quoteFacts.mediaTranscript !== undefined
        ? { mediaTranscript: row.quoteFacts.mediaTranscript }
        : {}),
      callout: {
        ...row.quoteFacts,
        hasLiked: null,
        hasReposted: null,
        updates: this.updates.get(id) ?? [],
        quotedCallout: null,
      },
    };
  }
  /** Public discussion context: absence/hidden/unmapped are distinct local states.
   * Hidden author identity never leaves this accessor. Missing projection is not absence.
   */
  discussionContext(id: string) {
    const row = this.callouts.get(id);
    if (!row) return { kind: "unknown" } as const;
    if (row.hidden || row.deleted) return { kind: "unavailable" } as const;
    if (!row.facts) return { kind: "unmapped" } as const;
    return {
      kind: "visible",
      authorId: row.authorId,
      callout: structuredClone(this.quote(id)),
    } as const;
  }
}

/** Optional operator-owned JSON file, bounded before allocation and before the server listens. */
export function loadCalloutsStore(path: string): CalloutsStore {
  const fd = openSync(path, constants.O_RDONLY | constants.O_NONBLOCK);
  try {
    const stat = fstatSync(fd);
    const maxBytes = 8 * 1024 * 1024;
    if (!stat.isFile() || stat.size > maxBytes)
      fail("input must be a regular file of at most 8 MiB");
    const bytes = Buffer.alloc(stat.size + 1);
    let size = 0;
    while (size < bytes.length) {
      const count = readSync(fd, bytes, size, bytes.length - size, null);
      if (!count) break;
      size += count;
    }
    if (size !== stat.size) fail("file changed during read");
    return new CalloutsStore(
      JSON.parse(
        new TextDecoder("utf-8", { fatal: true }).decode(
          bytes.subarray(0, size),
        ),
      ),
    );
  } finally {
    closeSync(fd);
  }
}
