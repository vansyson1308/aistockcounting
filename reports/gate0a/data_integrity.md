# Gate 0A data integrity audit

**Primary dataset (SoccerTrack v2): NETWORK-BLOCKED in this environment** — huggingface.co (sole distribution channel) is denied by the environment egress policy (gateway CONNECT 403; alternates GDrive/Kaggle/hf-mirror/Zenodo/GitHub-Pages also denied; the reachable GitHub toolkit repo contains no data). This audit therefore covers the one real GT segment lawfully obtainable here: the SoccerTrack v1 sample (25 s, fixed wide-view full-pitch camera, 11v11) committed in github.com/AtomScott/SoccerTrack — used strictly as preparatory real-GT evidence for evaluator validation and the O1 oracle, never as Gate verdict evidence or training data. The same auditor runs unchanged against the full v2 snapshot at handoff (see ml/gate0a/fetch_data.md).

## v1_sample

- gt: `data/gate0a_prep/v1_sample/gt.txt` (sha256 `cd2f1f4e2dc0eb8c…`)
- rows 16500, invalid 0, duplicates 0, parse issues 0
- frames 750 in [1, 750], gaps 0
- tracks 22, intra-track holes 0
- objects/frame [22, 22], bbox extent [4286.0, 891.9]
