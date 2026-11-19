#!/bin/sh
# Daily encrypted backup: PostgreSQL dump + encrypted file store (/data), AES-256 (openssl, PBKDF2).
# Files in /data are already AES-GCM encrypted by the app; the archive is encrypted again with BACKUP_PASSPHRASE.
set -eu
STAMP=$(date +%Y%m%d-%H%M%S)
OUT=/backups/lz-$STAMP.tar.gz.enc
TMP=$(mktemp -d)
pg_dump -h db -U lz -d lernzentrum -Fc -f "$TMP/db.dump"
tar -C /data -czf "$TMP/data.tar.gz" .
tar -C "$TMP" -czf - db.dump data.tar.gz | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE -out "$OUT"
rm -rf "$TMP"
find /backups -name 'lz-*.tar.gz.enc' -mtime +"${BACKUP_KEEP_DAYS:-14}" -delete
echo "backup ok: $OUT ($(du -h "$OUT" | cut -f1))"
# Optional off-site copy (Hetzner Storage Box): configure rclone/sftp on the host to sync ./backups.
