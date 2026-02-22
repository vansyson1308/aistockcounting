#!/usr/bin/env bash
set -euo pipefail

ARCHIVE=${1:?Usage: restore_minio.sh <minio.tar.gz>}
MINIO_DATA_DIR=${MINIO_DATA_DIR:-/var/lib/docker/volumes/aistockcounting_minio_data/_data}
mkdir -p "$MINIO_DATA_DIR"

tar -xzf "$ARCHIVE" -C "$MINIO_DATA_DIR"
echo "MinIO data restored to $MINIO_DATA_DIR"
