import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

export async function compareBaseline(path, screenshot, update = false) {
  if (update) {
    await mkdir(dirname(path), { recursive: true });
    await writeFile(path, screenshot);
    return;
  }
  let expected;
  try { expected = await readFile(path); }
  catch (error) {
    if (error.code !== "ENOENT") throw error;
    throw new Error(`Missing baseline: ${path}. Inspect screenshots before using UPDATE_VISUAL_BASELINES=1.`);
  }
  if (!expected.equals(screenshot)) throw new Error(`Screenshot differs: ${path}. Inspect actual screenshot; do not update blindly.`);
}
