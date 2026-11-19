// Copies the single source of truth (../config/brand.json) into the frontend before dev/build.
import { copyFileSync, existsSync } from "node:fs";
const src = new URL("../../config/brand.json", import.meta.url);
const dst = new URL("../src/brand.json", import.meta.url);
if (existsSync(src)) copyFileSync(src, dst);
