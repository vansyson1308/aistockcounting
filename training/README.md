# TrayAgent detector: data → YOLOX → ONNX → OpenCV 5

The runtime never imports PyTorch or Ultralytics. It loads `models/trayagent_v1.onnx`
with `cv2.dnn.readNetFromONNX` (OpenCV 5, `ENGINE_AUTO`). This folder produces
that file reproducibly.

## 0. Environments
```bash
make backend-venv                                   # .venv (runtime, tests, tooling)
python3 -m venv .venv-train
.venv-train/bin/pip install -r training/requirements-yolox.txt
.venv-train/bin/pip install --no-deps --no-build-isolation yolox==0.3.0   # Apache-2.0
.venv/bin/pip install -r tools/labeling/requirements.txt                  # cvat-sdk 2.13.0
```

## 1. Photos → labeling pool
Put the owner's photos in `datasets/vj_items/raw/`, hard cases (glare, blur, dense) in
`raw/hard/`, yesterday/today pairs in `raw/pairs/` and demo trays in `raw/demo/`.
```bash
python tools/labeling/ingest_raw.py            # EXIF orientation, face blur, content-addressed names
```

## 2. Pre-label → CVAT review (human in the loop)
```bash
python tools/labeling/prelabel.py --backend owlv2          # open-vocabulary pre-labels (or --backend classical)
make cvat-up
python tools/labeling/cvat_tasks.py create-task --folder datasets/vj_items/images/all \
       --name trayagent-v1 --prelabels datasets/vj_items/prelabels_yolo11.zip
# ... the owner reviews every image in CVAT (docs/competition/LABELING_HOWTO.md) ...
python tools/labeling/cvat_tasks.py export-yolo --task-id <id>
python tools/labeling/cvat_tasks.py unpack-export          # → datasets/vj_items/labels/all/*.txt
```

## 3. Split 70/15/15 and freeze the test set
```bash
python tools/labeling/split_dataset.py --seed 42           # stratified by hard cases; writes splits/test.manifest.sha256
python tools/labeling/split_dataset.py --verify            # run before every evaluation
```
Once a frozen manifest exists, re-splitting never moves images into or out of test.

## 4. Train (fixed seed) and export
```bash
.venv-train/bin/python training/train_yolox.py all --config training/configs/yolox_trayagent.yaml
# GPU: uses the official yolox.core.Trainer. CPU: a minimal loop over the same Exp components.
```
The best checkpoint is chosen by val mAP@0.5 (never by test). Export writes
`models/trayagent_v1.onnx`, its sidecar `trayagent_v1.json` (input size, letterbox,
decode mode, seed, config hash, val AP) and `trayagent_v1.sha256`. It then verifies
that `cv2.dnn` loads the graph.

Commit the `.json` and `.sha256`, upload the `.onnx` to S3 (`MODEL_PATH=... scripts/aws/deploy.sh`),
and install it anywhere with `scripts/fetch_model.sh` (SHA-256 checked).

## 5. Evaluate on the frozen test set
```bash
python training/scripts/agent_eval.py --backend onnx --model models/trayagent_v1.onnx \
       --machine c7g.large --out reports/agentic
```
This writes `reports/agentic/RESULTS.md`, `results.csv`, `summary.json`, plots, and a
failure gallery. It refuses to run if the frozen test manifest does not verify.

## Verified in this repo (engineering checks, not results)
- 2026-09-25: the whole path (prepare → CPU train → export → `cv2.dnn` → `OnnxYoloxDetector`)
  was exercised on a *synthetic* 40-image set with YOLOX-nano at 320 px from scratch for
  40 epochs. The ONNX decoded through OpenCV 5 matched the PyTorch val AP in magnitude,
  which confirms the letterbox and grid-decode compatibility. The synthetic numbers are
  NOT results and are not reported anywhere.
