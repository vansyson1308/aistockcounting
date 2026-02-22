# Training Workflow (Ultralytics YOLO)

## 1) Create training venv
```bash
python -m venv .venv-train
source .venv-train/bin/activate
pip install -r training/requirements-train.txt
```

## 2) Verify dataset structure
Expected:
- `datasets/vj_items/images/{train,val,test}`
- `datasets/vj_items/labels/{train,val,test}`
- `datasets/vj_items/data.yaml`

Quick check:
```bash
python tools/labeling/validate_dataset.py --root datasets/vj_items
```

## 3) Train
```bash
python training/scripts/train.py --config training/configs/yolo_v1.yaml
```

## 4) Evaluate
```bash
python training/scripts/eval.py --run-dir outputs/vj_items/<run_dir>
python training/scripts/count_accuracy.py --run-dir outputs/vj_items/<run_dir>
```

## 5) Export model artifact
```bash
python training/scripts/export.py --run-dir outputs/vj_items/<run_dir> --version v0001
```
Produces:
- `models/vj_items/v0001/best.pt`
- optional `best.onnx`
- `manifest.json`

## 6) Use model in backend
Set env:
```bash
MOCK_MODE=false
MODEL_PT_PATH=models/vj_items/v0001/best.pt
# optional
MODEL_ONNX_PATH=models/vj_items/v0001/best.onnx
```
Then run smoke test:
```bash
python backend/tools/model_smoke_test.py --image scripts/generated_sample.jpg
```
