"""Pure helpers of the demo video pipeline (demo/video/compose.py)."""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("yaml")
_p = Path(__file__).resolve().parents[2] / "demo" / "video" / "compose.py"
_spec = importlib.util.spec_from_file_location("compose", _p)
compose = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compose)


def test_srt_time_format() -> None:
    assert compose.srt_time(0) == "00:00:00,000"
    assert compose.srt_time(3723.456) == "01:02:03,456"


def test_srt_cues_cover_the_speech_span_in_order() -> None:
    text = (
        "First sentence here. Second one is a little bit longer than the first. Third!"
    )
    cues = compose.srt_cues(text, start=10.0, speech=9.0)
    assert len(cues) == 3
    assert cues[0][0] == pytest.approx(10.0)
    assert cues[-1][1] == pytest.approx(19.0)
    assert all(a < b for a, b, _ in cues)
    assert all(
        cues[i][1] == pytest.approx(cues[i + 1][0]) for i in range(len(cues) - 1)
    )


def test_long_sentences_are_split_for_readability() -> None:
    text = " ".join(["word"] * 60) + "."
    assert all(len(c[2]) <= 90 for c in compose.srt_cues(text, 0, 20))
