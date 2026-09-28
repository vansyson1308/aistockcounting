"""Oracle-vs-Real bottleneck decomposition (§16) — evidence, not impression.

Inputs per clip: metrics for O1, O2, O3, P4 (and P4_noteam, P3), detector
recall for GT boxes >= 40 px, ReID diagnostics. Thresholds come from the
frozen diagnostic contract. Every delta is quantified in the output.
"""

from __future__ import annotations

LABELS = ("DETECTION-LIMITED", "REID-LIMITED", "ASSOCIATION-LIMITED",
          "TEAM-LIMITED", "MIXED", "UNDETERMINED")


def _g(m: dict | None, key: str) -> float | None:
    if not m or m.get(key) is None:
        return None
    return float(m[key])


def classify_clip(variants: dict[str, dict], recall40: float | None,
                  reid: dict | None, rules: dict, deta_min: float,
                  recall_min: float) -> dict:
    o1, o2, o3, p4 = (variants.get(k) for k in ("O1", "O2", "O3", "P4"))
    p4nt, p3 = variants.get("P4_noteam"), variants.get("P3")
    ev: dict = {}
    fired: dict[str, float] = {}

    o3_assa, p4_assa = _g(o3, "assa"), _g(p4, "assa")
    if o3_assa is not None and p4_assa is not None:
        ev["detection_gap_assa_O3_minus_P4"] = round(o3_assa - p4_assa, 4)
        ev["detection_gap_hota_O3_minus_P4"] = round(_g(o3, "hota") - _g(p4, "hota"), 4)
    ev["P4_deta"] = _g(p4, "deta")
    ev["recall_ge40px"] = recall40
    det_weak = (ev["P4_deta"] is not None and ev["P4_deta"] < deta_min) or (
        recall40 is not None and recall40 < recall_min)
    if det_weak and o3_assa is not None and o3_assa >= rules["strong_oracle_assa"]:
        fired["DETECTION-LIMITED"] = ev.get("detection_gap_assa_O3_minus_P4", 0.0) or 0.0
    elif (ev.get("detection_gap_assa_O3_minus_P4") or 0.0) >= rules["detection_gap_min"] and (
        o3_assa is not None and o3_assa >= rules["strong_oracle_assa"]):
        fired["DETECTION-LIMITED"] = ev["detection_gap_assa_O3_minus_P4"]

    o1_assa, o2_assa = _g(o1, "assa"), _g(o2, "assa")
    if o1_assa is not None and o2_assa is not None:
        ev["reid_gain_assa_O2_minus_O1"] = round(o2_assa - o1_assa, 4)
    wt = None
    if reid:
        w = reid.get("within_team_top1_retrieval") or {}
        vals = [v for v in w.values() if v is not None]
        wt = min(vals) if vals else None
        if wt is None:
            t = reid.get("top1_retrieval") or {}
            vals = [v for v in t.values() if v is not None]
            wt = min(vals) if vals else None
    ev["reid_top1_weakest"] = wt
    reid_no_gain = ev.get("reid_gain_assa_O2_minus_O1") is not None and (
        ev["reid_gain_assa_O2_minus_O1"] < rules["reid_gain_min"])
    reid_poor = wt is not None and wt < rules["reid_within_team_top1_weak"]
    if reid_no_gain and reid_poor and o1_assa is not None and o1_assa >= rules["association_weak_assa"]:
        fired["REID-LIMITED"] = round(rules["reid_within_team_top1_weak"] - wt, 4)

    o3_int = _g(o3, "identity_integrity")
    ev["O3_assa"], ev["O3_identity_integrity"] = o3_assa, o3_int
    if o3_assa is not None and (o3_assa < rules["association_weak_assa"] or (
            o3_int is not None and o3_int < rules["association_weak_integrity"])):
        gap = max(rules["association_weak_assa"] - o3_assa,
                  (rules["association_weak_integrity"] - o3_int) if o3_int is not None else 0.0)
        fired["ASSOCIATION-LIMITED"] = round(gap, 4)

    team_acc = _g(p3, "team_accuracy") if p3 else None
    ev["team_accuracy"] = team_acc
    if p4nt and p4 and _g(p4nt, "assa") is not None and p4_assa is not None:
        ev["team_veto_harm_assa_P4noteam_minus_P4"] = round(_g(p4nt, "assa") - p4_assa, 4)
    team_harm = (ev.get("team_veto_harm_assa_P4noteam_minus_P4") or 0.0) >= rules["team_veto_harm_min"]
    if (team_acc is not None and team_acc < rules["team_accuracy_weak"]) or team_harm:
        fired["TEAM-LIMITED"] = round(max(ev.get("team_veto_harm_assa_P4noteam_minus_P4") or 0.0,
                                          (rules["team_accuracy_weak"] - team_acc) if team_acc is not None else 0.0), 4)

    primary = {k: v for k, v in fired.items() if k != "TEAM-LIMITED"}
    if not variants or p4 is None or o3 is None:
        label = "UNDETERMINED"
    elif len(primary) >= 2:
        label = "MIXED"
    elif len(primary) == 1:
        label = next(iter(primary))
    elif "TEAM-LIMITED" in fired:
        label = "TEAM-LIMITED"
    else:
        label = "NONE-DOMINANT"  # all gates healthy on this clip
    return {"label": label, "fired": fired, "evidence": ev}


def classify(per_clip: dict[str, dict]) -> dict:
    """Aggregate clip labels → dominant label (evidence-weighted)."""
    tally: dict[str, float] = {}
    for _clip, r in per_clip.items():
        for lab, mag in r["fired"].items():
            tally[lab] = tally.get(lab, 0.0) + max(float(mag), 1e-6)
    labels = [r["label"] for r in per_clip.values()]
    if not per_clip or all(lab == "UNDETERMINED" for lab in labels):
        dominant = "UNDETERMINED"
    elif all(lab == "NONE-DOMINANT" for lab in labels):
        dominant = "NONE-DOMINANT"
    else:
        primary = {k: v for k, v in tally.items() if k != "TEAM-LIMITED"}
        if len(primary) >= 2 and sorted(primary.values())[-2] >= 0.5 * max(primary.values()):
            dominant = "MIXED"
        elif primary:
            dominant = max(primary, key=primary.get)
        else:
            dominant = "TEAM-LIMITED" if tally else "NONE-DOMINANT"
    return {"dominant": dominant, "evidence_weight": {k: round(v, 4) for k, v in tally.items()},
            "per_clip": per_clip, "labels_vocabulary": [*LABELS, "NONE-DOMINANT"]}
