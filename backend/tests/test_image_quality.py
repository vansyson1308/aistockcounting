import numpy as np
import pytest

from app.utils.image_quality import ImageQuality, assess_image_quality
from tests.fixtures.synth_tray import make_tray


def test_return_shape_is_unchanged() -> None:
    q = assess_image_quality(make_tray().jpeg())
    assert isinstance(q, ImageQuality)
    assert isinstance(q.score, float) and 0 <= q.score <= 1
    assert isinstance(q.flags, list)
    for key in ("brightness", "contrast", "edge_energy", "glare_ratio"):
        assert key in q.metrics  # legacy keys kept for the truth layer
    for key in ("blur_var", "tray_coverage", "brightness_p99"):
        assert key in q.metrics


def test_clean_tray_has_no_flags() -> None:
    q = assess_image_quality(make_tray(seed=3).image)
    assert q.flags == []
    assert q.score == 1.0


@pytest.mark.parametrize(
    ("kwargs", "flag"),
    [
        ({"glare": 0.2}, "glare"),
        ({"blur": 31}, "blurry"),
        ({"tray_frac": 0.3}, "tray_not_found"),
    ],
)
def test_degradations_raise_flags(kwargs, flag) -> None:
    q = assess_image_quality(make_tray(**kwargs).image)
    assert flag in q.flags
    assert q.score < 1.0


def test_low_light_flag() -> None:
    dark = (make_tray().image * 0.25).astype(np.uint8)
    assert "low_light" in assess_image_quality(dark).flags


def test_full_frame_dark_velvet_is_not_low_light() -> None:
    q = assess_image_quality(make_tray(tray_frac=1.0).image)
    assert "low_light" not in q.flags
    assert q.metrics["tray_coverage"] > 0.9


def test_glare_ratio_orders_with_glare_amount() -> None:
    a = assess_image_quality(make_tray(glare=0.0).image).metrics["glare_ratio"]
    b = assess_image_quality(make_tray(glare=0.05).image).metrics["glare_ratio"]
    c = assess_image_quality(make_tray(glare=0.2).image).metrics["glare_ratio"]
    assert a < b < c


def test_blur_metric_decreases_with_blur() -> None:
    sharp = assess_image_quality(make_tray().image).metrics["blur_var"]
    soft = assess_image_quality(make_tray(blur=9).image).metrics["blur_var"]
    assert soft < sharp / 3
