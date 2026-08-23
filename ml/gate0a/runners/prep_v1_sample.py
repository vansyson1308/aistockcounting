"""Convert the SoccerTrack v1 sample bbdf CSV to MOTChallenge gt.txt.

The v1 repository (github.com/AtomScott/SoccerTrack) commits one real
ground-truth segment, `notebooks/02_user_guide/assets/sample_bbdf.csv`:
750 frames (~25 s @ 30 fps) of a fixed wide-view full-pitch camera,
22 players (TeamID 0/1) + ball (TeamID 3). We use it as REAL-GT
preparatory evidence (evaluator sanity checks, O1 oracle) while the
primary SoccerTrack v2 data is network-blocked in this environment.
It is NOT Gate 0A verdict evidence and is never used for training.

Players only (ball excluded, matching the v2 MOT protocol). Output:
MOT rows `frame,id,x,y,w,h,1,-1,-1,-1` (1-based frames) + a teams sidecar
`id,team` for team-aware experiments.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

BALL_TEAM = "3"


def convert(src: Path, out_dir: Path) -> dict:
    with open(src) as f:
        rows = list(csv.reader(f))
    teams, players, attrs = rows[0][1:], rows[1][1:], rows[2][1:]
    data = rows[4:]

    # Column groups: consecutive 5-attribute blocks per (team, player).
    objects: list[tuple[str, str, int]] = []  # (team, player, first_col_idx)
    i = 0
    while i < len(teams):
        assert attrs[i] == "bb_left", f"unexpected attr layout at col {i}"
        objects.append((teams[i], players[i], i))
        i += 5

    track_ids: dict[tuple[str, str], int] = {}
    for team, player, _ in objects:
        if team != BALL_TEAM:
            track_ids[(team, player)] = len(track_ids) + 1

    out_dir.mkdir(parents=True, exist_ok=True)
    gt_path = out_dir / "gt.txt"
    n_rows = 0
    with open(gt_path, "w") as out:
        for r in data:
            frame = int(r[0]) + 1  # MOT frames are 1-based
            for team, player, col in objects:
                if team == BALL_TEAM:
                    continue
                vals = r[1 + col : 1 + col + 4]
                if any(v in ("", "nan") for v in vals):
                    continue
                x, y, w, h = (float(v) for v in vals)
                if w <= 0 or h <= 0:
                    continue
                tid = track_ids[(team, player)]
                out.write(f"{frame},{tid},{x:.2f},{y:.2f},{w:.2f},{h:.2f},1,-1,-1,-1\n")
                n_rows += 1

    with open(out_dir / "teams.csv", "w") as tf:
        tf.write("track_id,team\n")
        for (team, _player), tid in sorted(track_ids.items(), key=lambda kv: kv[1]):
            tf.write(f"{tid},{team}\n")

    info = {
        "source": str(src),
        "n_frames": len(data),
        "n_tracks": len(track_ids),
        "n_boxes": n_rows,
        "fps_nominal": 30,
        "note": "SoccerTrack v1 sample; players only; preparatory evidence only",
    }
    (out_dir / "info.txt").write_text(
        "\n".join(f"{k}: {v}" for k, v in info.items()) + "\n"
    )
    return info


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    info = convert(args.src, args.out)
    print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
