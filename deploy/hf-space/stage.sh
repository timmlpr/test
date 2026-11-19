#!/bin/sh
# Assemble the files a private Hugging Face Space needs (no tests, no local DBs, no node_modules, no secrets).
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${1:?usage: stage.sh <out-dir>}"
rm -rf "$OUT" && mkdir -p "$OUT/deploy/hf-space"
cp "$ROOT/deploy/hf-space/Dockerfile" "$ROOT/deploy/hf-space/README.md" "$OUT/"
cp "$ROOT/deploy/hf-space/start.sh" "$OUT/deploy/hf-space/"
cp -r "$ROOT/config" "$ROOT/legal" "$OUT/"
(cd "$ROOT" && tar --exclude=.venv --exclude=__pycache__ --exclude='*.db' --exclude=.devkeys --exclude=uploads --exclude=tests \
  --exclude=.pytest_cache --exclude=.ruff_cache --exclude=node_modules --exclude=.next --exclude=test-results --exclude=e2e \
  --exclude=frontend/src/config --exclude=frontend/src/content/legal --exclude=tsconfig.tsbuildinfo --exclude=next-env.d.ts \
  -cf - backend frontend) | tar -C "$OUT" -xf -
echo "staged: $(find "$OUT" -type f | wc -l) files, $(du -sh "$OUT" | cut -f1)"
