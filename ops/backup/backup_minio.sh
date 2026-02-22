#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR=${1:-/opt/vj-inventory/backups/$(date +%Y%m%d_%H%M%S)}
MINIO_DATA_DIR=${MINIO_DATA_DIR:-/var/lib/docker/volumes/aistockcounting_minio_data/_data}
mkdir -p "$BACKUP_DIR"

tar -czf "$BACKUP_DIR/minio.tar.gz" -C "$MINIO_DATA_DIR" .
echo "$BACKUP_DIR/minio.tar.gz"
