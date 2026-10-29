import type { FastifyInstance } from "fastify";
import {
  TradesQueryError,
  type UserTradesOptions,
  type UserTradesStore,
} from "./user-trades-store.js";

export const USER_TRADES_NATIVE_ROUTES = new Set(["GET /user-trades/{id}"]);

/** A developer API route inside the existing key-shape gate; no website alias. */
export function registerUserTradesRoutes(
  app: FastifyInstance,
  store: UserTradesStore,
): void {
  app.get("/v1/user-trades/:id", async (request, reply) => {
    try {
      const qs = new Map<string, string>();
      const input = request.url.includes("?")
        ? request.url.slice(request.url.indexOf("?") + 1)
        : "";
      for (const [key, value] of new URLSearchParams(input)) {
        if (
          !["mint", "chainId", "chain", "cursor", "limit", "types"].includes(
            key,
          ) ||
          qs.has(key)
        )
          throw new TradesQueryError();
        qs.set(key, value);
      }
      if (qs.has("chain")) {
        // Every documented chain lane is keyed by chain alone and serves trades
        // only, so these combinations are request errors before lane support.
        if (
          qs.has("chainId") ||
          qs.get("types")?.split(",").includes("transfers")
        )
          throw new TradesQueryError();
        return reply.code(501).send({
          statusCode: 501,
          error: "COMPATIBILITY_NOT_IMPLEMENTED",
          reason: "TRADES_CHAIN_LANE_UNAVAILABLE",
        });
      }
      const opts: UserTradesOptions = {};
      for (const name of ["chainId", "limit"] as const) {
        if (qs.has(name)) {
          const text = qs.get(name)!;
          if (
            !/^-?(?:0|[1-9]\d*)$/.test(text) ||
            !Number.isSafeInteger(Number(text))
          )
            throw new TradesQueryError();
          opts[name] = Number(text);
        }
      }
      if (qs.has("mint")) opts.mint = qs.get("mint");
      if (qs.has("cursor")) opts.cursor = qs.get("cursor");
      if (qs.has("types")) {
        const values = qs.get("types")!.split(",");
        if (
          values.length > 2 ||
          !values.every((value) => value === "trades" || value === "transfers")
        )
          throw new TradesQueryError();
        opts.types = values as UserTradesOptions["types"];
      }
      const result = store.page((request.params as { id: string }).id, opts);
      if (result === null)
        return reply.code(404).send({ statusCode: 404, error: "NOT_FOUND" });
      return reply
        .header("X-Reconstruction-Data-Source", store.dataSource)
        .header("X-Reconstruction-Observed-At", store.observedAt)
        .header("X-Reconstruction-Compatibility", "unqualified")
        .send(result);
    } catch (error) {
      if (error instanceof TradesQueryError)
        return reply
          .code(400)
          .send({ statusCode: 400, error: "INVALID_QUERY" });
      throw error;
    }
  });
}
