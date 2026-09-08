"""Software-mechanics tests for the cloud layer (never product evidence)."""

import pytest

from ml.gate0a.cloud import contract as C
from ml.gate0a.cloud.units import detect_scale, to_fraction, with_percent_fields


def test_detect_scale_and_to_fraction():
    assert detect_scale([0.55, 0.9]) == "fraction"
    assert detect_scale([55.0, 90.0]) == "percent"
    assert to_fraction(55.0, "percent") == pytest.approx(0.55)
    with pytest.raises(ValueError):
        detect_scale([0.5, 150.0])


def test_with_percent_fields_refuses_mixed_units():
    row = with_percent_fields({"hota": 0.4321, "id_switches": 3})
    assert row["hota_percent"] == 43.21 and "id_switches_percent" not in row
    with pytest.raises(ValueError):
        with_percent_fields({"hota": 43.21})


def test_contract_loads_and_hash_is_stable():
    c = C.load_contract()
    assert c["metric_units"]["canonical"] == "fraction"
    assert "128057" in c["data_scope"]["forbidden_match_ids"]
    assert C.contract_sha256() == C.contract_sha256()
    assert c["level2_criteria"]["open_play_hota_min"] == 0.40


def _ev(**kw):
    base = {"chain_ran_end_to_end": True, "clips_scored": ["OPEN", "DENSE", "FAR"],
            "open_p4_hota": 0.5, "open_p4_deta": 0.5, "recall_ge40px_combined": 0.9,
            "bottleneck_label": "DETECTION-LIMITED"}
    base.update(kw)
    return C.Evidence(**base)


def test_maturity_levels():
    c = C.load_contract()
    assert C.decide_maturity(c, _ev())["maturity"] == C.LEVEL_2
    assert C.decide_maturity(c, _ev(open_p4_hota=0.3))["maturity"] == C.LEVEL_15
    assert C.decide_maturity(c, _ev(chain_ran_end_to_end=False))["maturity"] == C.LEVEL_1
    assert C.decide_maturity(c, _ev(clips_scored=["OPEN"]))["maturity"] == C.LEVEL_1
    r = C.decide_maturity(c, _ev(bottleneck_label="UNDETERMINED"))
    assert r["maturity"] == C.LEVEL_15 and "bottleneck_identified" in r["missing"]
    assert r["not_a_gate_verdict"] is True and "NOT OFFICIAL" in r["banner"]
