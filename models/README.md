# Models

The ONNX weights are not committed. Only their provenance is:

| File | Purpose |
|---|---|
| `trayagent_v1.sha256` | Expected SHA-256 of `trayagent_v1.onnx`. `scripts/fetch_model.sh` refuses any other file. |
| `trayagent_v1.json` | Sidecar read by `backend/app/services/detector_cv.py`: input size, letterbox, decode mode, class names, training seed, config hash and val mAP@0.5. |
| `trayagent_v1.source` | Where to fetch the weights from (`s3://…` or `https://…`). |

Produce them with `python training/train_yolox.py all` (see `training/README.md`), then
upload the `.onnx` to S3 (`scripts/aws/deploy.sh` does this when `MODEL_PATH` is set).
Until real photos have been labeled and a model trained, these files do not exist.
The backend then reports `detector.ready=false` for `DETECTOR_BACKEND=onnx`, and the demo
runs on the labeled `classical` OpenCV baseline instead.
