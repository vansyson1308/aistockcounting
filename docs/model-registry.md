# Model Registry & Versioning

## Version convention
- Stored under `models/vj_items/<version>/`
- Recommended format: `v0001`, `v0002`, ...

Each version folder should contain:
- `best.pt`
- `best.onnx` (optional)
- `manifest.json`

## Selecting active model in backend
Use env variables:
- `MOCK_MODE=false`
- `MODEL_PT_PATH=models/vj_items/v0001/best.pt`
- `MODEL_ONNX_PATH=models/vj_items/v0001/best.onnx` (optional, preferred if exists)

Resolution order in backend:
1. ONNX path if file exists
2. PT path if file exists
3. fallback to mock behavior with warning log

## Roll forward / rollback
- Roll forward: set `MODEL_PT_PATH`/`MODEL_ONNX_PATH` to new version.
- Rollback: point env back to previous version and restart backend.

## Compare versions
Use each `manifest.json` fields:
- `metrics.val.map50`, `metrics.val.map5095`
- `count_accuracy.count_accuracy_val.json`
- `dataset_hash`
