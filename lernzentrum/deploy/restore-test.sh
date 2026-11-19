#!/bin/sh
# Restore test: decrypts the newest backup, restores the DB dump into a scratch database and checks the schema.
set -eu
LATEST=$(ls -1t /backups/lz-*.tar.gz.enc | head -1)
TMP=$(mktemp -d)
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$LATEST" | tar -C "$TMP" -xzf -
psql -h db -U lz -d postgres -qc "DROP DATABASE IF EXISTS lz_restore_test" -qc "CREATE DATABASE lz_restore_test"
pg_restore -h db -U lz -d lz_restore_test --no-owner "$TMP/db.dump"
TABLES=$(psql -h db -U lz -d lz_restore_test -tAc "select count(*) from information_schema.tables where table_schema='public'")
USERS=$(psql -h db -U lz -d lz_restore_test -tAc "select count(*) from users")
tar -tzf "$TMP/data.tar.gz" >/dev/null
psql -h db -U lz -d postgres -qc "DROP DATABASE lz_restore_test"
rm -rf "$TMP"
[ "$TABLES" -ge 25 ] || { echo "restore test FAILED: only $TABLES tables"; exit 1; }
echo "restore test ok: $LATEST ($TABLES tables, $USERS users)"
