#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from pathlib import Path
from urllib.parse import quote

from common import load_env_file


def run_cmd(cmd: str) -> str:
    p = subprocess.run(cmd, shell=True, check=False, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"Command failed: {cmd}\nstdout={p.stdout}\nstderr={p.stderr}")
    return p.stdout.strip()


def create_task(args: argparse.Namespace) -> None:
    files = sorted([p for p in Path(args.folder).iterdir() if p.is_file() and not p.name.startswith(".")])
    if not files:
        raise SystemExit("No files found in folder")

    payload = json.dumps({"name": args.name, "labels": [{"name": "item"}]})
    create_cmd = (
        f"curl -sS -u {shlex.quote(args.user)}:{shlex.quote(args.password)} "
        f"-H 'Content-Type: application/json' -d {shlex.quote(payload)} "
        f"{shlex.quote(args.url.rstrip('/'))}/api/tasks"
    )
    create_out = run_cmd(create_cmd)
    task = json.loads(create_out)
    task_id = task["id"]

    form_parts = " ".join([f"-F client_files[]=@{shlex.quote(str(f))}" for f in files])
    upload_cmd = (
        f"curl -sS -u {shlex.quote(args.user)}:{shlex.quote(args.password)} "
        f"-F image_quality=90 -F use_cache=true {form_parts} "
        f"{shlex.quote(args.url.rstrip('/'))}/api/tasks/{task_id}/data"
    )
    run_cmd(upload_cmd)
    print(f"Created task {task_id}: {args.name}")


def export_yolo(args: argparse.Namespace) -> None:
    out_zip = Path(args.out_zip)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    format_name = quote("YOLO 1.1")
    cmd = (
        f"curl -sS -u {shlex.quote(args.user)}:{shlex.quote(args.password)} "
        f"-L {shlex.quote(args.url.rstrip('/'))}/api/tasks/{args.task_id}/dataset?format={format_name} "
        f"-o {shlex.quote(str(out_zip))}"
    )
    run_cmd(cmd)
    print(f"Downloaded dataset export to {out_zip}")


def main() -> None:
    load_env_file(".env.cvat")
    load_env_file("cvat/.env.cvat")

    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.getenv("CVAT_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--user", default=os.getenv("CVAT_USER", "admin"))
    parser.add_argument("--password", default=os.getenv("CVAT_PASS", "admin123"))

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create-task")
    p_create.add_argument("--folder", required=True)
    p_create.add_argument("--name", required=True)

    p_export = sub.add_parser("export-yolo")
    p_export.add_argument("--task-id", required=True)
    p_export.add_argument("--out-zip", default="datasets/vj_items/cvat_export.zip")

    args = parser.parse_args()
    if args.cmd == "create-task":
        create_task(args)
    elif args.cmd == "export-yolo":
        export_yolo(args)


if __name__ == "__main__":
    main()
