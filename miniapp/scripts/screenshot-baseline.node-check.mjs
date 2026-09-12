import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { compareBaseline } from "./screenshot-baseline.mjs";

test("requires explicit baseline creation and catches differences", async () => {
  const directory = await mkdtemp(join(tmpdir(), "miniapp-visual-test-"));
  try {
    const path = join(directory, "baseline.png");
    await assert.rejects(compareBaseline(path, Buffer.from("original")), /Missing baseline/);
    await compareBaseline(path, Buffer.from("original"), true);
    await compareBaseline(path, Buffer.from("original"));
    await assert.rejects(compareBaseline(path, Buffer.from("changed")), /Screenshot differs/);
    await compareBaseline(path, Buffer.from("changed"), true);
    await compareBaseline(path, Buffer.from("changed"));
  } finally { await rm(directory, { recursive: true }); }
});
