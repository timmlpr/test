// Copies the single-source config (../config) and legal drafts (../legal) into the frontend before dev/build,
// so brand, prices and plan limits are never duplicated by hand.
import { cpSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const copy = (from, to) => {
  if (!existsSync(from)) return;
  mkdirSync(to, { recursive: true });
  for (const f of readdirSync(from)) if (/\.(json|md)$/.test(f)) cpSync(join(from, f), join(to, f));
};
copy(join(root, "config"), join(here, "..", "src", "config"));
copy(join(root, "legal"), join(here, "..", "src", "content", "legal"));
console.log("synced config + legal");
