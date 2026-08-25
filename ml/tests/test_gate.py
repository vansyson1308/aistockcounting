from pathlib import Path

from ml.eval.gate import GateInputs, Verdict, decide, load_thresholds

THRESHOLDS = load_thresholds(
    Path(__file__).resolve().parents[1] / "gate0a" / "thresholds.yaml"
)


def _inputs(**overrides):
    base = {
        "hota": 60.0,
        "deta": 62.0,
        "assa": 58.0,
        "idf1": 70.0,
        "identity_integrity_half": 0.93,
        "team_cluster_accuracy": 0.97,
        "dense_audit_systemic_failure": False,
        "offline_delta_hota": 3.5,
        "soccernet_hota": 72.0,
        "assa_well_detected": None,
    }
    base.update(overrides)
    return GateInputs(**base)


def test_pass_when_all_bars_met():
    verdict, reasons = decide(_inputs(), THRESHOLDS)
    assert verdict is Verdict.PASS
    assert any("ablation" in r for r in reasons)


def test_offline_delta_is_not_a_gate():
    """§X.4 v1.1: a strong online baseline with a tiny offline delta passes."""
    verdict, _ = decide(_inputs(offline_delta_hota=0.4), THRESHOLDS)
    assert verdict is Verdict.PASS


def test_conditional_when_deta_limited_near_miss():
    verdict, reasons = decide(
        _inputs(
            hota=50.0,  # short of 55 by 5 (≤ margin 8)
            deta=52.0,  # below deta_healthy_min → detection-limited
            assa=52.0,  # short of 55 by 3
            idf1=63.0,  # short of 65 by 2
            assa_well_detected=58.0,  # association healthy where detection is
        ),
        THRESHOLDS,
    )
    assert verdict is Verdict.CONDITIONAL_PASS
    assert any("DetA-limited" in r for r in reasons)


def test_fail_profile_association_limited():
    verdict, reasons = decide(
        _inputs(
            hota=48.0,
            deta=65.0,  # detection healthy
            assa=42.0,  # association broken
            idf1=50.0,
            identity_integrity_half=0.7,
            dense_audit_systemic_failure=True,
            offline_delta_hota=0.5,
        ),
        THRESHOLDS,
    )
    assert verdict is Verdict.FAIL
    assert any("AssA-limited" in r for r in reasons)


def test_inconclusive_for_mixed_profile():
    # Big miss but detection healthy and audit clean: neither CONDITIONAL
    # (not DetA-limited) nor FAIL (audit clean) → needs analysis.
    verdict, reasons = decide(
        _inputs(hota=45.0, deta=64.0, assa=46.0, idf1=55.0), THRESHOLDS
    )
    assert verdict is Verdict.INCONCLUSIVE
    assert any("analyze" in r for r in reasons)


def test_team_clustering_below_bar_blocks_pass():
    verdict, _ = decide(_inputs(team_cluster_accuracy=0.9), THRESHOLDS)
    assert verdict is not Verdict.PASS
