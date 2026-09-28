"""Metric unit discipline: never compare 0.55 against 55.

The evaluator emits fractions. Every report row carries the canonical
fraction AND an explicit `<name>_percent` twin, and any external number is
normalized through `to_fraction` before a comparison.
"""

from __future__ import annotations

RATE_METRICS = (
    "hota",
    "deta",
    "assa",
    "loca",
    "idf1",
    "completeness",
    "identity_integrity",
    "recall",
    "team_accuracy",
)


def detect_scale(values: list[float]) -> str:
    """Infer whether rate-like values are on the 0-1 or 0-100 scale.

    Values must be consistent: anything > 1.0 implies percent; a set that
    never exceeds 1.0 is fraction. Mixed inputs are refused loudly.
    """
    finite = [float(v) for v in values if v is not None]
    if not finite:
        return "fraction"
    if any(v < 0 for v in finite):
        raise ValueError("rate metrics cannot be negative")
    if all(v <= 1.0 for v in finite):
        return "fraction"
    if all(v <= 100.0 for v in finite) and any(v > 1.0 for v in finite):
        return "percent"
    raise ValueError(f"inconsistent metric scale in {finite[:6]}...")


def to_fraction(value: float, scale: str) -> float:
    if scale == "fraction":
        return float(value)
    if scale == "percent":
        return float(value) / 100.0
    raise ValueError(f"unknown scale {scale!r}")


def with_percent_fields(row: dict, keys: tuple[str, ...] = RATE_METRICS) -> dict:
    """Return a copy with `<key>_percent` twins for every rate metric present."""
    out = dict(row)
    for k in keys:
        if k in row and row[k] is not None and row[k] != "":
            v = float(row[k])
            if v > 1.0 + 1e-9:
                raise ValueError(f"{k}={v} is not a fraction; normalize first")
            out[f"{k}_percent"] = round(v * 100.0, 2)
    return out
