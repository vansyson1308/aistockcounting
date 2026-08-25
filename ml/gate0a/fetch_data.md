# SoccerTrack v2 acquisition (Gate 0A)

**Status in the authoring environment (2026-08-23): NETWORK-BLOCKED.**
The dataset is distributed exclusively via Hugging Face
(`atomscott/soccertrack-v2`); this remote environment's egress policy denies
`huggingface.co` (gateway CONNECT 403 — verified, see
`reports/gate0a/executive_report.md`). All alternates checked and denied:
Google Drive, GitHub Pages landing, Kaggle, hf-mirror, Zenodo. The GitHub
toolkit repo (reachable) contains no data files or release assets. Nothing
about the dataset itself blocks us — data is CC BY 4.0.

## Unblock options (either works)

1. **Allow `huggingface.co` (+ `cdn-lfs.huggingface.co`) in this Claude Code
   environment's network policy**, then rerun the Gate 0A runbook here for
   all CPU-valid stages (GPU stages still need option 2).
2. **Run on any GPU machine** (also needed for detector fine-tuning):

```bash
# ~ disk: annotations are small; panoramic 4K videos are large (est. tens of
# GB per match; verify with the size printout before full download).
pip install -U huggingface_hub
python - <<'PY'
from huggingface_hub import snapshot_download
# 1) annotations + metadata only (small; enough for split/audit/sanity/O1):
snapshot_download("atomscott/soccertrack-v2", repo_type="dataset",
                  allow_patterns=["mot/*", "*.md", "*.json", "*.yaml"],
                  local_dir="data/soccertrack-v2")
# 2) videos for the frozen VAL + TEST matches first (O2/O3, detector eval):
pats = [f"interim/{m}/*" for m in ("118578", "128057", "132831")]
snapshot_download("atomscott/soccertrack-v2", repo_type="dataset",
                  allow_patterns=pats, local_dir="data/soccertrack-v2")
# 3) TRAIN match videos (detector fine-tuning) as disk permits.
PY
```

Record immediately after download:
- dataset repo revision (commit hash printed by snapshot_download);
- `sha256sum` manifest of every `gt.txt` and video actually used;
- both go into `reports/gate0a/data_integrity.md` (run
  `ml/gate0a/runners/audit_data.py`).

Layout expected by the runners (native dataset layout):
```
data/soccertrack-v2/
  mot/<match_id>/<1st_half|2nd_half>/gt/gt.txt     # train/val shape
  mot/<match_id>_<1st|2nd>/gt/gt.txt + seqinfo.ini # test-sequence shape
  interim/<match_id>/<match_id>_calibrated_panorama_<half>.mp4
```

Datasets and weights never enter Git (`data/` is gitignored).
