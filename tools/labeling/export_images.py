#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import boto3
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from common import load_env_file, write_manifest


async def run(args: argparse.Namespace) -> None:
    load_env_file(".env")

    db_url = args.database_url
    engine = create_async_engine(db_url)

    q = """
    SELECT id, image_path, tray_id, staff_id, created_at
    FROM counts
    WHERE image_path IS NOT NULL
    """
    params: dict = {}
    if args.date_from:
        q += " AND created_at >= :date_from"
        params["date_from"] = args.date_from
    if args.date_to:
        q += " AND created_at <= :date_to"
        params["date_to"] = args.date_to
    if args.tray_id:
        q += " AND tray_id = :tray_id"
        params["tray_id"] = args.tray_id
    q += " ORDER BY created_at DESC"
    if args.limit:
        q += " LIMIT :limit"
        params["limit"] = args.limit

    minio = boto3.client(
        "s3",
        endpoint_url=f"http://{args.minio_endpoint}",
        aws_access_key_id=args.minio_access_key,
        aws_secret_access_key=args.minio_secret_key,
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    async with engine.begin() as conn:
        rows = (await conn.execute(text(q), params)).mappings().all()

    for row in rows:
        record_id = str(row["id"])
        source_key = row["image_path"]
        ext = Path(source_key).suffix or ".jpg"
        filename = f"{record_id}{ext}"
        target = out_dir / filename
        if not target.exists():
            obj = minio.get_object(Bucket=args.minio_bucket, Key=source_key)
            target.write_bytes(obj["Body"].read())

        with Image.open(target) as img:
            img.verify()

        manifest_rows.append(
            {
                "image_filename": filename,
                "tray_id": row.get("tray_id") or "",
                "staff_id": row.get("staff_id") or "",
                "created_at": str(row.get("created_at") or ""),
                "record_id": record_id,
                "source_key": source_key,
            }
        )

    write_manifest(manifest_rows, out_dir.parent / "manifest.csv")
    print(f"Exported {len(manifest_rows)} images to {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--tray-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", default="datasets/vj_items/images/all")
    parser.add_argument("--database-url", default="postgresql+asyncpg://postgres:postgres@localhost:5432/stockdb")
    parser.add_argument("--minio-endpoint", default="localhost:9000")
    parser.add_argument("--minio-access-key", default="minioadmin")
    parser.add_argument("--minio-secret-key", default="minioadmin")
    parser.add_argument("--minio-bucket", default="tray-images")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
