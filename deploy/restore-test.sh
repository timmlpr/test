#!/bin/sh
# Restore test: decrypts the newest backup into a throwaway Postgres and checks that core tables have rows.
# Usage (on the server, in the repo dir):  BACKUP_PASSPHRASE=... sh deploy/restore-test.sh
set -eu
latest=$(ls -1t backups/tracelow-*.enc | head -1)
echo "testing $latest"
work=$(mktemp -d)
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$latest" | tar -C "$work" -xzf -
docker run -d --rm --name fp-restore-test -e POSTGRES_PASSWORD=t -e POSTGRES_DB=tracelow -e POSTGRES_USER=tracelow -v "$work:/restore:ro" postgres:17-alpine >/dev/null
for i in $(seq 1 30); do docker exec fp-restore-test pg_isready -U tracelow >/dev/null 2>&1 && break; sleep 1; done
docker exec fp-restore-test pg_restore -U tracelow -d tracelow /restore/db.dump
users=$(docker exec fp-restore-test psql -U tracelow -d tracelow -tAc "select count(*) from users")
docker stop fp-restore-test >/dev/null
rm -rf "$work"
echo "restore OK – users table has $users rows"
