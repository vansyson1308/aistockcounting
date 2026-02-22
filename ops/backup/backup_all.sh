#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT=${BACKUP_ROOT:-/opt/vj-inventory/backups}
STAMP=${STAMP:-$(date +%Y%m%d_%H%M%S)}
TARGET="$BACKUP_ROOT/$STAMP"
mkdir -p "$TARGET"

./ops/backup/backup_postgres.sh "$TARGET" >/dev/null
./ops/backup/backup_minio.sh "$TARGET" >/dev/null

POST_SIZE=$(stat -c%s "$TARGET/postgres.dump")
MINIO_SIZE=$(stat -c%s "$TARGET/minio.tar.gz")
POST_SHA=$(sha256sum "$TARGET/postgres.dump" | awk '{print $1}')
MINIO_SHA=$(sha256sum "$TARGET/minio.tar.gz" | awk '{print $1}')

cat > "$TARGET/manifest.json" <<MANIFEST
{
  "timestamp": "$STAMP",
  "postgres": {"file": "postgres.dump", "size": $POST_SIZE, "sha256": "$POST_SHA"},
  "minio": {"file": "minio.tar.gz", "size": $MINIO_SIZE, "sha256": "$MINIO_SHA"}
}
MANIFEST

echo "Backup complete: $TARGET"
