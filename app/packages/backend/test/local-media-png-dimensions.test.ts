import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test, { type TestContext } from "node:test";
import Fastify from "fastify";
import { registerLocalMediaRoutes } from "../src/local-media-routes.js";
import { LOCAL_MEDIA_PREFIX as P, LocalMediaStore } from "../src/local-media-store.js";

// Synthetic 1x1 PNG test image; no user upload or captured production media.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK1cAAAAASUVORK5CYII=",
  "base64",
);
const TOKEN = "synthetic-test-only-local-capability-123456789";

async function setup(t: TestContext) {
  const directory = await mkdtemp(join(tmpdir(), "local-media-png-"));
  const store = await LocalMediaStore.open(directory);
  const app = Fastify();
  registerLocalMediaRoutes(app, { store, token: TOKEN });
  await app.ready();
  t.after(async () => {
    await app.close();
    await store.close();
    await rm(directory, { recursive: true, force: true });
  });
  return app;
}

function withDimensions(width: number, height: number) {
  const bytes = Buffer.from(PNG);
  bytes.writeUInt32BE(width, 16);
  bytes.writeUInt32BE(height, 20);
  return bytes;
}

function upload(app: Awaited<ReturnType<typeof setup>>, payload: Buffer) {
  return app.inject({
    method: "POST",
    url: `${P}/images`,
    headers: { authorization: `Bearer ${TOKEN}`, "content-type": "image/png" },
    payload,
  });
}

test("PNG IHDR dimensions above 2^31-1 are rejected like zero dimensions", async (t) => {
  const app = await setup(t);
  for (const [width, height] of [[0x80000000, 1], [1, 0x80000000], [0xffffffff, 0xffffffff]]) {
    const response = await upload(app, withDimensions(width, height));
    assert.equal(response.statusCode, 415, `${width}x${height}`);
    assert.equal(response.json().code, "LOCAL_MEDIA_IMAGE_TYPE");
  }
  const largest = await upload(app, withDimensions(0x7fffffff, 0x7fffffff));
  assert.equal(largest.statusCode, 201);
  assert.equal(largest.json().mime, "image/png");
});
