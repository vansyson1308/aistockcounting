"""Procedural tray fixtures for TESTS ONLY.

These images are drawn with OpenCV primitives: a dark velvet tray on a light
table, with shiny metallic "items" (rings and pendants). They exist so every
tool and controller branch can be tested before real photos arrive. They are
never used for training, evaluation or any reported number (see
docs/competition/SPEC.md §5 and the honesty rules in STATUS.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class SynthTray:
    image: np.ndarray  # BGR uint8
    boxes: list[tuple[float, float, float, float]]  # x, y, w, h (image coords)
    tray_quad: np.ndarray  # 4x2 float32, TL, TR, BR, BL
    meta: dict = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.boxes)

    def jpeg(self, quality: int = 92) -> bytes:
        ok, buf = cv2.imencode(".jpg", self.image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        assert ok
        return buf.tobytes()


def _draw_item(
    img: np.ndarray, cx: int, cy: int, r: int, rng: np.random.Generator
) -> None:
    gold = np.array([60, 170, 215], dtype=np.float64)  # BGR
    silver = np.array([200, 200, 205], dtype=np.float64)
    base = gold if rng.random() < 0.6 else silver
    base = np.clip(base + rng.normal(0, 8, 3), 0, 255)
    kind = rng.integers(0, 2)
    if kind == 0:  # ring: thick annulus
        cv2.circle(
            img, (cx, cy), r, tuple(float(v) for v in base), thickness=max(3, r // 3)
        )
    else:  # pendant: filled ellipse
        cv2.ellipse(
            img,
            (cx, cy),
            (r, int(r * 0.75)),
            float(rng.integers(0, 180)),
            0,
            360,
            tuple(float(v) for v in base),
            -1,
        )
    # specular highlight
    hx, hy = cx - r // 3, cy - r // 3
    cv2.circle(img, (hx, hy), max(2, r // 5), (250, 250, 250), -1)


def make_tray(
    n_items: int = 12,
    *,
    seed: int = 0,
    size: tuple[int, int] = (960, 1280),  # H, W
    item_radius: tuple[int, int] = (22, 32),
    glare: float = 0.0,
    blur: int = 0,
    perspective: float = 0.0,
    tray_frac: float = 0.8,
    exclude_items: list[int] | None = None,
    positions_seed: int | None = None,
) -> SynthTray:
    """Draw a tray with ``n_items`` items.

    glare: 0..1, the fraction of the tray covered by a saturated specular blob.
    blur: Gaussian kernel size (odd; 0 disables).
    perspective: 0..0.3, how strongly the tray corners are pushed inward.
    exclude_items: indices of items to leave out. With a fixed
        ``positions_seed`` this simulates "yesterday vs today" pairs.
    """
    rng = np.random.default_rng(seed)
    pos_rng = np.random.default_rng(seed if positions_seed is None else positions_seed)
    h, w = size
    img = np.full((h, w, 3), (205, 212, 218), dtype=np.uint8)  # light table
    img = cv2.add(img, rng.integers(0, 6, (h, w, 3), dtype=np.uint8))

    th, tw = int(h * tray_frac), int(w * tray_frac)
    ty, tx = (h - th) // 2, (w - tw) // 2
    tray = np.full((th, tw, 3), (40, 28, 34), dtype=np.uint8)  # dark velvet
    tray = cv2.add(tray, pos_rng.integers(0, 10, (th, tw, 3), dtype=np.uint8))

    # item layout on a jittered grid inside the tray
    boxes_local: list[tuple[float, float, float, float]] = []
    cols = max(1, int(np.ceil(np.sqrt(n_items * tw / th))))
    rows = max(1, int(np.ceil(n_items / cols)))
    cell_w, cell_h = tw / cols, th / rows
    excluded = set(exclude_items or [])
    idx = 0
    for r_i in range(rows):
        for c_i in range(cols):
            if idx >= n_items:
                break
            rad = int(pos_rng.integers(item_radius[0], item_radius[1] + 1))
            rad = int(min(rad, cell_w * 0.4, cell_h * 0.4))
            jx = pos_rng.uniform(-0.15, 0.15) * cell_w
            jy = pos_rng.uniform(-0.15, 0.15) * cell_h
            cx = int((c_i + 0.5) * cell_w + jx)
            cy = int((r_i + 0.5) * cell_h + jy)
            item_rng = np.random.default_rng((positions_seed or seed) * 1000 + idx)
            if idx not in excluded:
                _draw_item(tray, cx, cy, rad, item_rng)
                boxes_local.append((cx - rad, cy - rad, 2 * rad, 2 * rad))
            idx += 1

    img[ty : ty + th, tx : tx + tw] = tray
    quad = np.array(
        [[tx, ty], [tx + tw, ty], [tx + tw, ty + th], [tx, ty + th]], dtype=np.float32
    )
    boxes = [(x + tx, y + ty, bw, bh) for (x, y, bw, bh) in boxes_local]

    if glare > 0:
        overlay = img.copy()
        gw, gh = int(tw * np.sqrt(glare) * 1.1), int(th * np.sqrt(glare) * 0.9)
        center = (tx + tw // 2, ty + th // 3)
        cv2.ellipse(
            overlay, center, (gw // 2, gh // 2), 15, 0, 360, (255, 255, 255), -1
        )
        overlay = cv2.GaussianBlur(overlay, (0, 0), 6)
        mask = np.zeros((h, w), np.uint8)
        cv2.ellipse(mask, center, (gw // 2, gh // 2), 15, 0, 360, 255, -1)
        img = np.where(mask[..., None] > 0, overlay, img)
        img[mask > 0] = (253, 253, 253)

    if perspective > 0:
        d = perspective
        src = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
        dst = np.array(
            [[w * d, h * d * 0.5], [w * (1 - d), h * d * 0.3], [w, h], [0, h]],
            dtype=np.float32,
        )
        m = cv2.getPerspectiveTransform(src, dst)
        img = cv2.warpPerspective(img, m, (w, h), borderValue=(205, 212, 218))
        quad = cv2.perspectiveTransform(quad[None], m)[0]
        warped: list[tuple[float, float, float, float]] = []
        for x, y, bw, bh in boxes:
            pts = np.array(
                [[x, y], [x + bw, y], [x + bw, y + bh], [x, y + bh]], np.float32
            )
            p = cv2.perspectiveTransform(pts[None], m)[0]
            x0, y0 = p.min(axis=0)
            x1, y1 = p.max(axis=0)
            warped.append((float(x0), float(y0), float(x1 - x0), float(y1 - y0)))
        boxes = warped

    if blur and blur > 1:
        k = blur if blur % 2 == 1 else blur + 1
        img = cv2.GaussianBlur(img, (k, k), 0)

    return SynthTray(
        image=img,
        boxes=[tuple(float(v) for v in b) for b in boxes],
        tray_quad=quad.astype(np.float32),
        meta={
            "seed": seed,
            "glare": glare,
            "blur": blur,
            "perspective": perspective,
            "n_items": n_items,
        },
    )
