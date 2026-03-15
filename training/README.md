# Training Workflow (Ultralytics YOLOv8)

## Quick Start (1 command)

```bash
# Activate training venv
source .venv-train/bin/activate

# Run full pipeline: validate → train → evaluate → export
make train-pipeline VERSION=v0001

# Or run everything including dataset split:
make train-all VERSION=v0001
```

---

## First-Time Training Guide (80-150 images)

### How many images do I need?

| Images | Expected Quality | Notes |
|--------|-----------------|-------|
| 50-79  | Baseline, low accuracy | Only for quick testing |
| **80-120** | **Good for small shops** | Recommended minimum |
| **120-150** | **Very good accuracy** | Best value for effort |
| 200-300 | Excellent | Diminishing returns after this |
| 300+   | Marginal improvement | Only if many jewelry types |

**Why this works with few images:** YOLOv8n uses transfer learning from COCO (pretrained on 330K images). Your 100 images with ~30 items each = ~3,000 labeled objects, which is plenty for single-class detection.

### How to take good photos

1. **Bird's-eye view**: Shoot directly from above the tray, same angle as when using the app
2. **Vary tray fullness**:
   - Empty trays (0 items) — 5-10 photos
   - Sparse (1-10 items) — 15-20 photos
   - Medium (10-30 items) — 30-40 photos
   - Dense (30+ items) — 30-40 photos
3. **Vary lighting**: Natural light, shop lighting, slight shadows
4. **Include all jewelry types** your shop carries (rings, necklaces, earrings, bracelets)
5. **Avoid blurry photos** — each item must be distinguishable
6. **Use the same phone/camera** you'll use in production
7. **Resolution**: At least 640x640px (any modern phone camera is fine)

### Labeling with CVAT

```bash
# 1. Start CVAT
make cvat-up
# Open http://127.0.0.1:8081, login admin/admin123

# 2. Create labeling task
make cvat-create-task FOLDER=datasets/vj_items/images/all NAME="vj-round1"

# 3. Label in CVAT UI (draw bounding boxes around each jewelry item)
#    - Single class: "item"
#    - Each piece = 1 box (pair of earrings = 2 boxes)
#    - Tight boxes, allow overlaps
#    See docs/labeling-guidelines.md for full rules

# 4. Export annotations
make cvat-export-yolo TASK_ID=1 OUT_ZIP=datasets/vj_items/cvat_export.zip

# 5. Unzip labels into labels/all/
unzip -o datasets/vj_items/cvat_export.zip -d datasets/vj_items/labels/all/
```

### Full Pipeline (step by step)

```bash
# Split images AND labels into train/val/test (80/10/10)
make dataset-split

# Validate dataset format
make dataset-validate

# Train + evaluate + export (one command)
make train-pipeline VERSION=v0001

# Deploy
# Set env vars as shown in pipeline output, then:
make backend-dev
make model-smoke IMAGE=path/to/test_image.jpg
```

---

## Detailed Step-by-Step

### 1) Create training venv
```bash
make train-venv
source .venv-train/bin/activate
```

### 2) Verify dataset structure
Expected:
- `datasets/vj_items/images/{train,val,test}`
- `datasets/vj_items/labels/{train,val,test}`
- `datasets/vj_items/data.yaml`

Quick check:
```bash
make dataset-validate
```

### 3) Train
```bash
python training/scripts/train.py --config training/configs/yolo_v1.yaml
```

Override hyperparameters:
```bash
python training/scripts/train.py --config training/configs/yolo_v1.yaml --epochs 100 --batch 16
```

### 4) Evaluate
```bash
python training/scripts/eval.py --run-dir outputs/vj_items/<run_dir>
python training/scripts/count_accuracy.py --run-dir outputs/vj_items/<run_dir>
```

### 5) Export model artifact
```bash
python training/scripts/export.py --run-dir outputs/vj_items/<run_dir> --version v0001
```
Produces:
- `models/vj_items/v0001/best.pt`
- optional `best.onnx`
- `manifest.json`

### 6) Use model in backend
Set env:
```bash
MOCK_MODE=false
MODEL_PT_PATH=models/vj_items/v0001/best.pt
# optional
MODEL_ONNX_PATH=models/vj_items/v0001/best.onnx
MODEL_VERSION=v0001
```
Then run smoke test:
```bash
make model-smoke IMAGE=scripts/generated_sample.jpg
```

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| "No labels found" | Labels not in `labels/all/` before split | Unzip CVAT export to `labels/all/`, then `make dataset-split` |
| Low mAP (<0.5) | Too few images or poor labeling | Add more images, review labeling guidelines |
| Training very slow on CPU | Default is `device: cpu` | Edit config: `device: 0` if you have an NVIDIA GPU |
| "CUDA out of memory" | Batch too large for GPU | Reduce batch size: `--batch 4` |
| Tiny box warnings | Jewelry too small in frame | Take closer photos or zoom in during labeling |
| `dataset-validate` fails | Label format issues | Check CVAT export format is "YOLO 1.1" |

## Training Config Reference

File: `training/configs/yolo_v1.yaml`

```yaml
model: yolov8n.pt    # YOLOv8 nano (fastest, good for single-class)
data: datasets/vj_items/data.yaml
epochs: 50           # 50 is a good default; increase to 100 if underfitting
imgsz: 640           # Input image size
batch: 8             # Increase if you have GPU memory
seed: 42             # Reproducibility
patience: 20         # Early stopping after 20 epochs without improvement
device: cpu          # Change to 0 for NVIDIA GPU
```
