#!/usr/bin/env python3
"""CVAT helpers (server v2.13.0; SDK pinned to cvat-sdk==2.13.0 in
tools/labeling/requirements.txt).

    create-task    upload a folder of images, optionally importing pre-labels
                   (the YOLO 1.1 zip written by prelabel.py) in the same call
    export-yolo    download the human-reviewed annotations as YOLO 1.1
    unpack-export  turn a YOLO 1.1 export into labels/all/<stem>.txt
"""

from __future__ import annotations

import argparse
import os
import shutil
import zipfile
from pathlib import Path

from common import load_env_file

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def _client(args: argparse.Namespace):
    from cvat_sdk import make_client

    return make_client(args.url, credentials=(args.user, args.password))


def create_task(args: argparse.Namespace) -> None:
    from cvat_sdk.api_client import models

    files = sorted(
        str(p)
        for p in Path(args.folder).iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    if not files:
        raise SystemExit("No images found in folder")
    spec = models.TaskWriteRequest(
        name=args.name,
        labels=[models.PatchedLabelRequest(name="item", type="rectangle")],
    )
    with _client(args) as client:
        task = client.tasks.create_from_data(
            spec=spec,
            resources=files,
            data_params={"image_quality": 90, "use_cache": True},
            annotation_path=args.prelabels or "",
            annotation_format="YOLO 1.1",
        )
    print(f"Created task {task.id}: {args.name} ({len(files)} images)")
    if args.prelabels:
        print(f"Imported pre-labels from {args.prelabels}; review every image in CVAT.")


def export_yolo(args: argparse.Namespace) -> None:
    out_zip = Path(args.out_zip)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with _client(args) as client:
        client.tasks.retrieve(int(args.task_id)).export_dataset(
            "YOLO 1.1", str(out_zip), include_images=False
        )
    print(f"Downloaded YOLO 1.1 export to {out_zip}")


def unpack_export(zip_path: Path, labels_dir: Path) -> int:
    """Extract ``obj_train_data/*.txt`` from a YOLO 1.1 export into ``labels_dir``."""
    labels_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            p = Path(info.filename)
            if p.suffix == ".txt" and p.parent.name == "obj_train_data":
                with zf.open(info) as src, (labels_dir / p.name).open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                n += 1
    return n


def main() -> None:
    load_env_file(".env.cvat")
    load_env_file("cvat/.env.cvat")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("CVAT_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--user", default=os.getenv("CVAT_USER", "admin"))
    parser.add_argument("--password", default=os.getenv("CVAT_PASS", "admin123"))
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create-task")
    p_create.add_argument("--folder", required=True)
    p_create.add_argument("--name", required=True)
    p_create.add_argument(
        "--prelabels", default=None, help="YOLO 1.1 zip from prelabel.py"
    )

    p_export = sub.add_parser("export-yolo")
    p_export.add_argument("--task-id", required=True)
    p_export.add_argument("--out-zip", default="datasets/vj_items/cvat_export.zip")

    p_unpack = sub.add_parser("unpack-export")
    p_unpack.add_argument("--zip", default="datasets/vj_items/cvat_export.zip")
    p_unpack.add_argument("--labels", default="datasets/vj_items/labels/all")

    args = parser.parse_args()
    if args.cmd == "create-task":
        create_task(args)
    elif args.cmd == "export-yolo":
        export_yolo(args)
    else:
        n = unpack_export(Path(args.zip), Path(args.labels))
        print(f"Wrote {n} label files to {args.labels}")


if __name__ == "__main__":
    main()
