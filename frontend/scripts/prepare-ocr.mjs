// Serve OCR code/model from our own origin; farmer documents never go to a CDN.
import { copyFile, mkdir, readdir } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dest = resolve(root, "public/ocr");
await mkdir(dest, { recursive: true });
await copyFile(resolve(root, "node_modules/tesseract.js/dist/worker.min.js"), resolve(dest, "worker.min.js"));
const core = resolve(root, "node_modules/tesseract.js-core");
for (const file of await readdir(core)) {
  if (/\.wasm(?:\.js)?$/.test(file)) await copyFile(resolve(core, file), resolve(dest, file));
}
await copyFile(resolve(root, "node_modules/@tesseract.js-data/eng/4.0.0_best_int/eng.traineddata.gz"), resolve(dest, "eng.traineddata.gz"));
