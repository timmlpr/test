#!/bin/sh
# Encrypted daily backup: pg_dump + uploads → AES-256 (openssl, PBKDF2) → /backups. Keeps BACKUP_KEEP_DAYS days.
set -eu
[ -n "${BACKUP_PASSPHRASE:-}" ] || { echo "BACKUP_PASSPHRASE missing – refusing to write unencrypted backups"; exit 1; }
ts=$(date -u +%Y%m%dT%H%M%SZ)
out=/backups/tracelow-$ts.tar.gz.enc
tmp=$(mktemp -d)
pg_dump -h db -U tracelow -d tracelow -Fc -f "$tmp/db.dump"
[ -d /data ] && tar -C /data -czf "$tmp/data.tgz" . 2>/dev/null || true
tar -C "$tmp" -czf - . | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE -out "$out"
rm -rf "$tmp"
find /backups -name 'tracelow-*.enc' -mtime +"${BACKUP_KEEP_DAYS:-30}" -delete
echo "backup written: $out"
