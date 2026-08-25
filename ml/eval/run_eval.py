"""CLI: evaluate a MOT-format prediction against ground truth.

Usage:
    python -m ml.eval.run_eval GT.txt PRED.txt [--online-pred ONLINE.txt]
        [--hota] [--json OUT.json]

`--online-pred` additionally evaluates an online-only baseline and reports the
offline-vs-online ablation delta. `--hota` requires the trackeval package.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ml.eval.metrics import evaluate_tracking
from ml.eval.mot_io import read_mot
from ml.eval.trackeval_wrapper import TrackEvalUnavailable, hota_from_frames


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gt", type=Path)
    parser.add_argument("pred", type=Path)
    parser.add_argument("--online-pred", type=Path, default=None)
    parser.add_argument("--hota", action="store_true")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    gt = read_mot(args.gt)
    pred = read_mot(args.pred)
    result: dict = {"final": evaluate_tracking(gt, pred).as_dict()}

    if args.hota:
        try:
            result["final"].update(
                {k: round(v * 100, 2) for k, v in hota_from_frames(gt, pred).items()}
            )
        except TrackEvalUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.online_pred is not None:
        online = read_mot(args.online_pred)
        result["online_baseline"] = evaluate_tracking(gt, online).as_dict()
        if args.hota:
            try:
                result["online_baseline"].update(
                    {
                        k: round(v * 100, 2)
                        for k, v in hota_from_frames(gt, online).items()
                    }
                )
            except TrackEvalUnavailable as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
        if "hota" in result["final"] and "hota" in result["online_baseline"]:
            result["ablation_offline_delta_hota"] = round(
                result["final"]["hota"] - result["online_baseline"]["hota"], 2
            )
        result["ablation_offline_delta_idf1"] = round(
            result["final"]["idf1"] - result["online_baseline"]["idf1"], 4
        )

    text = json.dumps(result, indent=2)
    print(text)
    if args.json:
        args.json.write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
