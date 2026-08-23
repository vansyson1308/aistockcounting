# ml/ — Football tracking core (Phase 0a seed)

Self-contained ML package for the football-tracking pivot (plan §Y). No
dependency on the legacy `backend/` app. Built in Phase 0a as the scaffolding
Gate 0A needs; grows into the production pipeline modules after the gate.

| Module | Contents |
|---|---|
| `ml.track` | Purity-first online tracker (plan §H): CV Kalman, two-stage association incl. low-confidence detections, appearance fusion, **ambiguity termination** (fragment rather than gamble), lost-state reacquisition |
| `ml.associate` | Offline reconciliation seed (plan §I): tracklet split via embedding clustering, constrained best-first merge with reachability/team/overlap constraints |
| `ml.eval` | MOT IO; native IDF1 / ID-switch / completeness / identity-integrity metrics; TrackEval wrapper for HOTA (official implementation, not reimplemented); Gate 0A verdict logic |
| `ml/gate0a` | Runbook + machine-readable §X.4 thresholds |

Setup and tests (from the repo root):

```bash
python3 -m venv .venv-ml && . .venv-ml/bin/activate
pip install -r ml/requirements-dev.txt
pytest ml/tests tools/camsim/tests -q
python scripts/license_gate.py
```

Design rules carried from the plan: no AGPL/GPL/HL3 imports (CI-enforced);
clean-room implementations from papers only; every module unit-tested on
synthetic data; nothing here touches the legacy app.
