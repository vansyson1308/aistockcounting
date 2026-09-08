"""CLI entry point (used by the Kaggle notebook and by HF Jobs alike).

    python -m ml.gate0a.cloud.run_stage --stage all --out /kaggle/working/gate0a_outputs \
        --scratch /kaggle/tmp/gate0a_scratch

Exit codes: 0 done · 3 OWNER UI ACTION REQUIRED (external authorization) · 1 error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from ml.gate0a.cloud import BANNER, stage0, stage1, stage2
from ml.gate0a.cloud.artifact_manifest import now_iso
from ml.gate0a.cloud.contract import CONTRACT_PATH, load_contract
from ml.gate0a.cloud.secrets import describe_presence, get_secret

CONFIG_PATH = Path(__file__).with_name("config") / "stage012.yaml"
REPO_ROOT = Path(__file__).resolve().parents[3]


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def real_detector_factory(cfg: dict, device: str):
    def make():
        from ml.gate0a.cloud.detector_adapter import load_detector

        return load_detector(cfg["detector"], device=device, token=get_secret("HF_TOKEN"))
    return make


def real_embedder_factory(cfg: dict, device: str):
    def make():
        from ml.gate0a.cloud.reid_adapter import load_embedder

        return load_embedder(cfg["reid"], device=device)
    return make


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=["0", "1", "2", "all"], default="all")
    ap.add_argument("--out", type=Path, default=Path("/kaggle/working/gate0a_outputs"))
    ap.add_argument("--scratch", type=Path, default=Path("/kaggle/tmp/gate0a_scratch"))
    ap.add_argument("--config", type=Path, default=CONFIG_PATH)
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args(argv)

    print(BANNER)
    cfg = load_config(args.config)
    contract = load_contract(CONTRACT_PATH)
    args.out.mkdir(parents=True, exist_ok=True)
    args.scratch.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(args.scratch / cfg["storage"]["hf_cache_subdir"]))
    print("secrets present:", describe_presence())
    started = now_iso()
    (args.out / "state").mkdir(parents=True, exist_ok=True)
    (args.out / "state" / "run_started.json").write_text(json.dumps({"started_at": started}) + "\n")

    stages = ["0", "1", "2"] if args.stage == "all" else [args.stage]
    try:
        if "0" in stages:
            acq = stage0.acquire(cfg, args.out, args.scratch, contract)
            st0 = stage0.analyze(cfg, contract, args.out, acq)
            print(f"[stage0] windows frozen sha256={st0['windows_sha256'][:16]}… "
                  f"fps={st0['fps']} frames={st0['n_video_frames']} units={st0['evaluator_units']}")
        if "1" in stages:
            st1 = stage1.run(cfg, contract, args.out, real_detector_factory(cfg, args.device),
                             real_embedder_factory(cfg, args.device), device=args.device)
            print(f"[stage1] margin={st1['selected_margin']} recall>=40px={st1['recall_ge40']} "
                  f"chain_ran={st1['chain_ran']}")
        if "2" in stages:
            st2 = stage2.run(cfg, contract, args.out, REPO_ROOT, started)
            print(f"[stage2] maturity: {st2['maturity']['maturity']} | bottleneck: "
                  f"{st2['bottleneck']['dominant']}")
    except stage0.OwnerActionRequired as exc:
        print(f"\n{BANNER}\n\nCLOUD RUN PACKAGE: READY — external authorization missing ({exc}).\n")
        print(stage0.OWNER_ACTION)
        return 3
    print(f"\ndone → {stage0.report_dir(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
