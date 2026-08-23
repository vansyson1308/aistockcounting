"""Camsim CLI: rank candidate camera configurations over the pitch.

Usage (from the repo root):
    python -m tools.camsim.run --preset B --height 15 --out outputs/camsim
    python -m tools.camsim.run --all --heights 8 12 15 20 --out outputs/camsim

Outputs per configuration: JSON summary (px/m, expected player bbox height,
elevation, occlusion proxy, threshold coverages) and, when matplotlib is
available and --plots is set, PNG heatmaps. Detection/OCR thresholds are the
plan's working numbers; Gate 0A replaces the detection floor with the
measured px-height-vs-recall curve.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from tools.camsim.model import PitchSpec, pitch_grid
from tools.camsim.occlusion import OcclusionConfig, occlusion_rate_by_zone
from tools.camsim.presets import PRESETS, RigConfig

PLAYER_HEIGHT_M = 1.8
# Working thresholds (plan sections F.1/F.3): replaced by measured curves at
# Gate 0A. Player bbox height in px:
DETECT_MIN_PX = 20.0
REID_MIN_PX = 40.0
OCR_MIN_PX = 110.0  # ~0.25 m digit at >=~15 px needs ~ this player height


@dataclass
class ZoneStats:
    min: float
    p10: float
    median: float
    max: float

    @classmethod
    def from_values(cls, values: np.ndarray) -> ZoneStats:
        v = values[np.isfinite(values)]
        if v.size == 0:
            return cls(float("nan"), float("nan"), float("nan"), float("nan"))
        return cls(
            float(np.min(v)),
            float(np.percentile(v, 10)),
            float(np.median(v)),
            float(np.max(v)),
        )


def evaluate_rig(
    rig: RigConfig,
    pitch: PitchSpec,
    grid_step_m: float = 1.0,
    occlusion_samples: int = 150,
) -> dict:
    pts = pitch_grid(pitch, grid_step_m)

    # Per-cell best camera (max vertical px/m — the identity-limiting axis).
    per_cam_v = np.stack([c.vertical_px_per_m(pts) for c in rig.cameras])
    per_cam_h = np.stack([c.horizontal_px_per_m(pts) for c in rig.cameras])
    per_cam_elev = np.stack([c.elevation_deg(pts) for c in rig.cameras])

    best_cam = np.nanargmax(
        np.where(np.isnan(per_cam_v), -np.inf, per_cam_v), axis=0
    )
    idx = np.arange(len(pts))
    v_px_per_m = per_cam_v[best_cam, idx]
    h_px_per_m = per_cam_h[best_cam, idx]
    elev = per_cam_elev[best_cam, idx]
    covered = np.isfinite(v_px_per_m)
    bbox_h_px = v_px_per_m * PLAYER_HEIGHT_M

    def coverage(threshold_px: float) -> float:
        return float(np.mean(np.nan_to_num(bbox_h_px, nan=0.0) >= threshold_px))

    # Occlusion proxy per camera, worst-relevant: evaluate on the camera that
    # owns most cells (single-mast rigs share a viewpoint anyway); for
    # distributed rigs report the min over cameras (a clump is "resolved" if
    # any camera sees it un-occluded).
    zone_x = np.linspace(-pitch.length_m / 2, pitch.length_m / 2, 7)
    zone_y = np.linspace(-pitch.width_m / 2, pitch.width_m / 2, 5)
    occ_cfg_open = OcclusionConfig(n_samples=occlusion_samples, set_piece=False)
    occ_cfg_set = OcclusionConfig(n_samples=occlusion_samples, set_piece=True)
    open_grids, open_rates, set_rates = [], [], []
    for cam in rig.cameras:
        g_open, r_open = occlusion_rate_by_zone(
            cam, pitch, occ_cfg_open, zone_x, zone_y
        )
        _, r_set = occlusion_rate_by_zone(cam, pitch, occ_cfg_set, zone_x, zone_y)
        open_grids.append(g_open)
        open_rates.append(r_open)
        set_rates.append(r_set)
    if len(rig.cameras) > 1 and rig.name == "D":
        occlusion_open = float(np.min(open_rates))
        occlusion_set = float(np.min(set_rates))
    else:
        occlusion_open = float(np.mean(open_rates))
        occlusion_set = float(np.mean(set_rates))

    summary = {
        "rig": rig.name,
        "description": rig.description,
        "n_cameras": len(rig.cameras),
        "grid_step_m": grid_step_m,
        "pitch_coverage_fraction": float(np.mean(covered)),
        "player_bbox_height_px": asdict(ZoneStats.from_values(bbox_h_px)),
        "vertical_px_per_m": asdict(ZoneStats.from_values(v_px_per_m)),
        "horizontal_px_per_m": asdict(ZoneStats.from_values(h_px_per_m)),
        "elevation_deg": asdict(ZoneStats.from_values(np.where(covered, elev, np.nan))),
        "coverage_detect_fraction": coverage(DETECT_MIN_PX),
        "coverage_reid_fraction": coverage(REID_MIN_PX),
        "coverage_ocr_fraction": coverage(OCR_MIN_PX),
        "occlusion_rate_open_play": occlusion_open,
        "occlusion_rate_set_piece": occlusion_set,
        "thresholds_px": {
            "detect": DETECT_MIN_PX,
            "reid": REID_MIN_PX,
            "ocr": OCR_MIN_PX,
        },
    }
    fields = {
        "points": pts,
        "bbox_h_px": bbox_h_px,
        "elevation_deg": elev,
        "occlusion_open_zone_grid": open_grids,
    }
    return {"summary": summary, "fields": fields}


def save_heatmaps(result: dict, pitch: PitchSpec, out_dir: Path) -> list[Path]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    pts = result["fields"]["points"]
    nx = len(np.unique(pts[:, 0]))
    ny = len(np.unique(pts[:, 1]))
    written = []
    for key, label in (
        ("bbox_h_px", "expected player bbox height (px)"),
        ("elevation_deg", "elevation angle (deg)"),
    ):
        grid = result["fields"][key].reshape(ny, nx)
        fig, ax = plt.subplots(figsize=(9, 6))
        im = ax.imshow(
            grid,
            origin="lower",
            extent=(
                -pitch.length_m / 2,
                pitch.length_m / 2,
                -pitch.width_m / 2,
                pitch.width_m / 2,
            ),
            aspect="equal",
        )
        ax.set_title(f"{result['summary']['rig']}: {label}")
        ax.set_xlabel("x (m) — camera mast at bottom")
        ax.set_ylabel("y (m)")
        fig.colorbar(im, ax=ax, shrink=0.8)
        path = out_dir / f"{result['summary']['rig']}_{key}.png"
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=sorted(PRESETS), default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--heights", type=float, nargs="*", default=[15.0])
    parser.add_argument("--grid-step", type=float, default=1.0)
    parser.add_argument("--occlusion-samples", type=int, default=150)
    parser.add_argument("--out", type=Path, default=Path("outputs/camsim"))
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args(argv)

    names = sorted(PRESETS) if args.all or not args.preset else [args.preset]
    pitch = PitchSpec()
    args.out.mkdir(parents=True, exist_ok=True)
    all_summaries = []
    for name in names:
        for height in args.heights:
            rig = PRESETS[name](pitch, height_m=height)
            result = evaluate_rig(
                rig,
                pitch,
                grid_step_m=args.grid_step,
                occlusion_samples=args.occlusion_samples,
            )
            result["summary"]["mount_height_m"] = height
            all_summaries.append(result["summary"])
            if args.plots:
                save_heatmaps(result, pitch, args.out)

    out_file = args.out / "summary.json"
    out_file.write_text(json.dumps(all_summaries, indent=2) + "\n")
    for s in all_summaries:
        print(
            f"{s['rig']}@{s['mount_height_m']:>4.1f}m  "
            f"bboxH min/p10/med = {s['player_bbox_height_px']['min']:.0f}/"
            f"{s['player_bbox_height_px']['p10']:.0f}/"
            f"{s['player_bbox_height_px']['median']:.0f} px  "
            f"detect/reid/ocr = {s['coverage_detect_fraction']:.0%}/"
            f"{s['coverage_reid_fraction']:.0%}/"
            f"{s['coverage_ocr_fraction']:.0%}  "
            f"elev min = {s['elevation_deg']['min']:.1f}°  "
            f"occl open/set = {s['occlusion_rate_open_play']:.1%}/"
            f"{s['occlusion_rate_set_piece']:.1%}"
        )
    print(f"summary → {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
