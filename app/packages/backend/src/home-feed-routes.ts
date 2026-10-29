import type { FastifyInstance, FastifyReply } from "fastify";
import {
  FEED_ASSET_CLASSES,
  FEED_CHAINS,
  HomeFeedCursorError,
  type FeedAssetClass,
  type FeedChain,
  type HomeFeedFilters,
  HomeFeedStore,
  defaultHomeFeedStore,
  isWellFormedUnicode,
} from "./home-feed-store.js";
import { errorBody } from "./users-routes.js";

const DATA_SOURCE_HEADER = "X-Reconstruction-Data-Source";
const COMPATIBILITY_HEADER = "X-Reconstruction-Compatibility";

const HOME_QUERY_KEYS = new Set([
  "page",
  "pageSize",
  "pageToken",
  "forceRefresh",
  "chain",
  "chains",
  "minMarketCapUsd",
  "maxMarketCapUsd",
  "minCostBasisUsd",
  "maxCostBasisUsd",
  "assetClasses",
  "includeFollowedHolders",
  "followedHoldersLimit",
  "recsys",
  "updatesLimit",
  "userId",
  "session_id",
  "device_id",
  "session_start_timestamp_ms",
  "country",
  "os",
  "platform",
]);

const NEW_QUERY_KEYS = new Set([
  "pageSize",
  "pageToken",
  "updatesLimit",
  "chain",
  "chains",
  "minCostBasisUsd",
  "maxCostBasisUsd",
  "minCalloutMarketCapUsd",
  "maxCalloutMarketCapUsd",
  "minMarketCapUsd",
  "maxMarketCapUsd",
  "assetClasses",
]);

const COUNT_QUERY_KEYS = new Set([
  "since",
  "chain",
  "chains",
  "minCostBasisUsd",
  "maxCostBasisUsd",
  "minCalloutMarketCapUsd",
  "maxCalloutMarketCapUsd",
  "minMarketCapUsd",
  "maxMarketCapUsd",
  "assetClasses",
]);

class HomeFeedRequestError extends Error {
  constructor(
    readonly statusCode: 400 | 501,
    readonly code: string,
    readonly field?: string,
  ) {
    super(code);
    this.name = "HomeFeedRequestError";
  }
}

function sendLocal(reply: FastifyReply, dataSource: string, body: unknown) {
  return reply
    .code(200)
    .header(DATA_SOURCE_HEADER, dataSource)
    .header(COMPATIBILITY_HEADER, "local-unqualified")
    .header("Cache-Control", "no-store")
    .send(body);
}

function failUnknownKeys(query: Record<string, unknown>, allowed: Set<string>) {
  const unknown = Object.keys(query).find((key) => !allowed.has(key));
  if (unknown !== undefined)
    throw new HomeFeedRequestError(400, "UNKNOWN_QUERY_PARAMETER", unknown);
}

function single(
  query: Record<string, unknown>,
  field: string,
  options: { required?: boolean; allowEmpty?: boolean } = {},
): string | undefined {
  const value = query[field];
  if (value === undefined) {
    if (options.required)
      throw new HomeFeedRequestError(400, "QUERY_REQUIRED", field);
    return undefined;
  }
  if (Array.isArray(value)) {
    throw new HomeFeedRequestError(400, "DUPLICATE_QUERY_PARAMETER", field);
  }
  if (
    typeof value !== "string" ||
    !isWellFormedUnicode(value) ||
    /[\u0000-\u001f\u007f]/u.test(value) ||
    (!options.allowEmpty && value.length === 0)
  ) {
    throw new HomeFeedRequestError(400, "INVALID_QUERY_PARAMETER", field);
  }
  return value;
}

function integer(
  query: Record<string, unknown>,
  field: string,
  minimum: number,
  maximum: number,
  fallback: number,
): number {
  const raw = single(query, field);
  if (raw === undefined) return fallback;
  if (!/^(?:0|[1-9]\d*)$/u.test(raw)) {
    throw new HomeFeedRequestError(400, "INVALID_INTEGER", field);
  }
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new HomeFeedRequestError(400, "INTEGER_OUT_OF_RANGE", field);
  }
  return value;
}

function number(
  query: Record<string, unknown>,
  field: string,
): number | undefined {
  const raw = single(query, field);
  if (raw === undefined) return undefined;
  if (!/^(?:0|[1-9]\d*)(?:\.\d+)?$/u.test(raw)) {
    throw new HomeFeedRequestError(400, "INVALID_NUMBER", field);
  }
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) {
    throw new HomeFeedRequestError(400, "INVALID_NUMBER", field);
  }
  return value;
}

function boolean(
  query: Record<string, unknown>,
  field: string,
): boolean | undefined {
  const raw = single(query, field);
  if (raw === undefined) return undefined;
  if (raw !== "true" && raw !== "false") {
    throw new HomeFeedRequestError(400, "INVALID_BOOLEAN", field);
  }
  return raw === "true";
}

function list<T extends string>(
  query: Record<string, unknown>,
  field: string,
  values: readonly T[],
): T[] {
  const raw = single(query, field);
  if (raw === undefined) return [];
  const items = raw.split(",");
  if (
    items.length === 0 ||
    items.length > values.length ||
    items.some((item) => item.length === 0 || !values.includes(item as T)) ||
    new Set(items).size !== items.length
  ) {
    throw new HomeFeedRequestError(400, "INVALID_QUERY_LIST", field);
  }
  return items as T[];
}

function boundedPair(
  query: Record<string, unknown>,
  minimumField: string,
  maximumField: string,
): [number | undefined, number | undefined] {
  const minimum = number(query, minimumField);
  const maximum = number(query, maximumField);
  if (minimum !== undefined && maximum !== undefined && maximum < minimum) {
    throw new HomeFeedRequestError(400, "CONTRADICTORY_BOUNDS", maximumField);
  }
  return [minimum, maximum];
}

function parseFilters(
  query: Record<string, unknown>,
  options: { calloutMarketCap: boolean },
): HomeFeedFilters {
  const chain = single(query, "chain");
  if (
    chain !== undefined &&
    chain !== "all" &&
    !FEED_CHAINS.includes(chain as FeedChain)
  ) {
    throw new HomeFeedRequestError(400, "INVALID_CHAIN", "chain");
  }
  const chains = list(query, "chains", FEED_CHAINS);
  if (chain !== undefined && chains.length > 0) {
    throw new HomeFeedRequestError(400, "CHAIN_FILTER_CONFLICT", "chains");
  }
  const [minMarketCapUsd, maxMarketCapUsd] = boundedPair(
    query,
    "minMarketCapUsd",
    "maxMarketCapUsd",
  );
  const [minCostBasisUsd, maxCostBasisUsd] = boundedPair(
    query,
    "minCostBasisUsd",
    "maxCostBasisUsd",
  );
  let minCalloutMarketCapUsd: number | undefined;
  let maxCalloutMarketCapUsd: number | undefined;
  if (options.calloutMarketCap) {
    [minCalloutMarketCapUsd, maxCalloutMarketCapUsd] = boundedPair(
      query,
      "minCalloutMarketCapUsd",
      "maxCalloutMarketCapUsd",
    );
  }
  return {
    chains:
      chains.length > 0
        ? chains
        : chain !== undefined && chain !== "all"
          ? [chain as FeedChain]
          : [],
    assetClasses: list(
      query,
      "assetClasses",
      FEED_ASSET_CLASSES,
    ) as FeedAssetClass[],
    minMarketCapUsd,
    maxMarketCapUsd,
    minCostBasisUsd,
    maxCostBasisUsd,
    minCalloutMarketCapUsd,
    maxCalloutMarketCapUsd,
  };
}

function handleError(error: unknown, reply: FastifyReply) {
  if (error instanceof HomeFeedRequestError) {
    return reply
      .code(error.statusCode)
      .send(
        errorBody(
          error.statusCode,
          error.code,
          error.field ? { field: error.field } : {},
        ),
      );
  }
  if (error instanceof HomeFeedCursorError) {
    return reply.code(400).send(errorBody(400, "INVALID_CURSOR"));
  }
  throw error;
}

export function registerHomeFeedRoutes(
  app: FastifyInstance,
  store: HomeFeedStore = defaultHomeFeedStore,
): void {
  app.get("/services/frontend/home-feed", async (request, reply) => {
    try {
      const query = request.query as Record<string, unknown>;
      failUnknownKeys(query, HOME_QUERY_KEYS);
      const page = integer(query, "page", 0, Number.MAX_SAFE_INTEGER, 0);
      const pageSize = integer(query, "pageSize", 1, 200, 150);
      const pageToken = single(query, "pageToken");
      if (pageToken && pageToken.length > 256) {
        throw new HomeFeedRequestError(400, "CURSOR_TOO_LONG", "pageToken");
      }
      if (pageToken && page !== 0) {
        throw new HomeFeedRequestError(400, "PAGINATION_MODE_CONFLICT", "page");
      }
      boolean(query, "forceRefresh");
      boolean(query, "recsys");
      integer(query, "updatesLimit", 1, 10, 10);
      const includeFollowedHolders = boolean(query, "includeFollowedHolders");
      integer(query, "followedHoldersLimit", 1, Number.MAX_SAFE_INTEGER, 3);
      const platform = single(query, "platform");
      if (platform !== undefined && platform !== "WEB" && platform !== "APP") {
        throw new HomeFeedRequestError(400, "INVALID_PLATFORM", "platform");
      }
      // Validate filters with every other supplied value, so a malformed
      // filter is a 400 even when a personalization hint is also present.
      const filters = parseFilters(query, { calloutMarketCap: false });
      const unsupported = [
        "userId",
        "session_id",
        "device_id",
        "session_start_timestamp_ms",
        "country",
        "os",
      ].find((field) => query[field] !== undefined);
      if (
        unsupported ||
        includeFollowedHolders === true ||
        platform === "APP"
      ) {
        throw new HomeFeedRequestError(
          501,
          "PERSONALIZED_FEED_UNAVAILABLE",
          unsupported ??
            (includeFollowedHolders ? "includeFollowedHolders" : "platform"),
        );
      }
      const response = store.ranked({
        filters,
        page,
        pageSize,
        pageToken,
      });
      return sendLocal(reply, store.dataSource, response);
    } catch (error) {
      return handleError(error, reply);
    }
  });

  app.get("/services/frontend/home-feed/new", async (request, reply) => {
    try {
      const query = request.query as Record<string, unknown>;
      failUnknownKeys(query, NEW_QUERY_KEYS);
      const pageSize = integer(query, "pageSize", 1, 50, 25);
      integer(query, "updatesLimit", 1, 10, 10);
      const pageToken = single(query, "pageToken");
      if (pageToken && pageToken.length > 512) {
        throw new HomeFeedRequestError(400, "CURSOR_TOO_LONG", "pageToken");
      }
      const response = store.newest({
        filters: parseFilters(query, { calloutMarketCap: true }),
        pageSize,
        pageToken,
      });
      return sendLocal(reply, store.dataSource, response);
    } catch (error) {
      return handleError(error, reply);
    }
  });

  app.get("/services/frontend/home-feed/new/count", async (request, reply) => {
    try {
      const query = request.query as Record<string, unknown>;
      failUnknownKeys(query, COUNT_QUERY_KEYS);
      const since = single(query, "since", { required: true });
      if (since!.length > 512) {
        throw new HomeFeedRequestError(400, "CURSOR_TOO_LONG", "since");
      }
      const response = store.countNew({
        filters: parseFilters(query, { calloutMarketCap: true }),
        since: since!,
      });
      return sendLocal(reply, store.dataSource, response);
    } catch (error) {
      return handleError(error, reply);
    }
  });
}
