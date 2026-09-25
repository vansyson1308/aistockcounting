"""Detection and counting metrics shared by training (val) and evaluation (test).

Pure numpy; boxes are (x, y, w, h) in pixels. AP uses VOC-style all-point
interpolation at a single IoU threshold (mAP@0.5 for our single class).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

Box = tuple[float, float, float, float]


def iou_matrix(a: Sequence[Box], b: Sequence[Box]) -> np.ndarray:
    if not a or not b:
        return np.zeros((len(a), len(b)))
    A = np.asarray(a, np.float64)
    B = np.asarray(b, np.float64)
    ax1, ay1, ax2, ay2 = A[:, 0], A[:, 1], A[:, 0] + A[:, 2], A[:, 1] + A[:, 3]
    bx1, by1, bx2, by2 = B[:, 0], B[:, 1], B[:, 0] + B[:, 2], B[:, 1] + B[:, 3]
    iw = np.clip(np.minimum(ax2[:, None], bx2) - np.maximum(ax1[:, None], bx1), 0, None)
    ih = np.clip(np.minimum(ay2[:, None], by2) - np.maximum(ay1[:, None], by1), 0, None)
    inter = iw * ih
    union = (A[:, 2] * A[:, 3])[:, None] + B[:, 2] * B[:, 3] - inter
    return inter / np.maximum(union, 1e-9)


def average_precision(
    preds: Sequence[Sequence[tuple[float, float, float, float, float]]],
    gts: Sequence[Sequence[Box]],
    iou_thr: float = 0.5,
) -> float:
    """AP at ``iou_thr`` over a dataset. ``preds[i]`` = [(x,y,w,h,score), ...]."""
    n_gt = sum(len(g) for g in gts)
    if n_gt == 0:
        return float("nan")
    records: list[tuple[float, int]] = []  # (score, is_tp)
    for p_img, g_img in zip(preds, gts, strict=True):
        order = sorted(range(len(p_img)), key=lambda i: -p_img[i][4])
        ious = iou_matrix([p_img[i][:4] for i in order], list(g_img))
        taken = np.zeros(len(g_img), bool)
        for rank, i in enumerate(order):
            tp = 0
            if len(g_img):
                j = int(np.argmax(ious[rank]))
                if ious[rank, j] >= iou_thr and not taken[j]:
                    taken[j] = True
                    tp = 1
            records.append((p_img[i][4], tp))
    if not records:
        return 0.0
    records.sort(key=lambda r: -r[0])
    tps = np.cumsum([r[1] for r in records])
    fps = np.cumsum([1 - r[1] for r in records])
    recall = tps / n_gt
    precision = tps / np.maximum(tps + fps, 1e-9)
    mrec = np.concatenate([[0.0], recall, [1.0]])
    mpre = np.concatenate([[0.0], precision, [0.0]])
    for k in range(len(mpre) - 2, -1, -1):
        mpre[k] = max(mpre[k], mpre[k + 1])
    idx = np.where(mrec[1:] != mrec[:-1])[0]
    return float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))


def count_metrics(
    pred_counts: Sequence[int], true_counts: Sequence[int]
) -> dict[str, float]:
    p = np.asarray(pred_counts, np.float64)
    t = np.asarray(true_counts, np.float64)
    if len(t) == 0:
        return {
            "n": 0,
            "mae": float("nan"),
            "exact": float("nan"),
            "within1": float("nan"),
        }
    err = p - t
    return {
        "n": int(len(t)),
        "mae": float(np.mean(np.abs(err))),
        "exact": float(np.mean(err == 0)),
        "within1": float(np.mean(np.abs(err) <= 1)),
        "mean_signed_error": float(np.mean(err)),
        # PRD-style count accuracy: 1 - |err| / true, floored at 0, averaged
        "count_accuracy": float(
            np.mean(np.clip(1 - np.abs(err) / np.maximum(t, 1), 0, 1))
        ),
    }


def read_yolo_labels(path, width: int, height: int) -> list[Box]:
    """YOLO txt (``cls cx cy w h`` normalized) -> pixel (x, y, w, h)."""
    from pathlib import Path

    boxes: list[Box] = []
    p = Path(path)
    if not p.exists():
        return boxes
    for line in p.read_text().splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        _, cx, cy, bw, bh = map(float, parts)
        boxes.append(
            ((cx - bw / 2) * width, (cy - bh / 2) * height, bw * width, bh * height)
        )
    return boxes
