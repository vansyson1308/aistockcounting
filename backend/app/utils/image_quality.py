import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter, ImageStat


@dataclass(frozen=True)
class ImageQuality:
    score: float
    flags: list[str]
    metrics: dict[str, float]


def assess_image_quality(image_bytes: bytes) -> ImageQuality:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    gray = image.convert("L")
    stat = ImageStat.Stat(gray)
    brightness = float(stat.mean[0])
    contrast = float(stat.stddev[0])

    # A light-weight blur proxy: low edge energy means the tray photo is soft.
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_stat = ImageStat.Stat(edges)
    edge_energy = float(edge_stat.mean[0])

    arr = np.asarray(image)
    glare_ratio = float(np.mean(np.all(arr > 245, axis=2)))

    flags: list[str] = []
    if brightness < 65:
        flags.append("low_light")
    if brightness > 225 or glare_ratio > 0.08:
        flags.append("glare")
    if contrast < 18 or edge_energy < 8:
        flags.append("blurry")

    score = 1.0
    score -= 0.25 if "low_light" in flags else 0
    score -= 0.25 if "glare" in flags else 0
    score -= 0.3 if "blurry" in flags else 0
    score = max(0.0, round(score, 2))

    return ImageQuality(
        score=score,
        flags=flags,
        metrics={
            "brightness": round(brightness, 2),
            "contrast": round(contrast, 2),
            "edge_energy": round(edge_energy, 2),
            "glare_ratio": round(glare_ratio, 4),
        },
    )
