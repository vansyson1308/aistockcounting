#!/usr/bin/env python3
"""Train the TrayAgent detector with YOLOX (Apache-2.0) and export it for OpenCV 5 DNN.

    python training/train_yolox.py prepare --config training/configs/yolox_trayagent.yaml
    python training/train_yolox.py train   --config ... [--device cuda|cpu]
    python training/train_yolox.py export  --config ... --ckpt outputs/yolox/<run>/best.pth
    python training/train_yolox.py all     --config ...

* ``prepare`` converts the frozen YOLO-txt splits (tools/labeling/split_dataset.py)
  into the COCO layout YOLOX reads: ``<root>/coco/{train2017,val2017}`` (symlinks)
  and ``annotations/instances_{train,val}2017.json``. The test split is never
  converted: it is only read by the evaluation script, through the ONNX model.
* ``train`` builds a YOLOX ``Exp`` from the YAML config (seed, depth/width, input
  size, epochs, augmentation). On CUDA it runs the official ``yolox.core.Trainer``.
  On CPU it runs a minimal loop over the same Exp components (data loader with
  mosaic, optimizer, warm-cos LR, EMA), because the official Trainer is CUDA-only.
  The best checkpoint is chosen by val mAP@0.5.
* ``export`` writes ``models/<name>.onnx`` (``decode_in_inference=False``, opset 11,
  input ``images`` 1×3×H×W BGR 0..255, top-left letterbox padded with 114) plus the
  sidecar ``models/<name>.json`` that ``backend/app/services/detector_cv.py`` reads,
  plus ``models/<name>.sha256``. It then checks that ``cv2.dnn`` loads the model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from training.metrics import average_precision, read_yolo_labels  # noqa: E402

PRESETS = {
    "nano": {"depth": 0.33, "width": 0.25, "depthwise": True},
    "tiny": {"depth": 0.33, "width": 0.375, "depthwise": False},
    "s": {"depth": 0.33, "width": 0.50, "depthwise": False},
    "m": {"depth": 0.67, "width": 0.75, "depthwise": False},
}
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def load_config(path: str | Path) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    cfg["_path"] = str(path)
    cfg["_sha256"] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return cfg


def seed_everything(seed: int) -> None:
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)


# --------------------------------------------------------------------------- prepare
def yolo_split_to_coco(root: Path, split: str) -> dict:
    import cv2

    images, annotations = [], []
    ann_id = 1
    img_dir, lbl_dir = root / "images" / split, root / "labels" / split
    for img_id, p in enumerate(sorted(img_dir.iterdir()), start=1):
        if p.suffix.lower() not in IMAGE_EXTS:
            continue
        img = cv2.imread(str(p))
        h, w = img.shape[:2]
        images.append({"id": img_id, "file_name": p.name, "width": w, "height": h})
        for x, y, bw, bh in read_yolo_labels(lbl_dir / f"{p.stem}.txt", w, h):
            annotations.append(
                {
                    "id": ann_id,
                    "image_id": img_id,
                    "category_id": 1,
                    "bbox": [round(x, 2), round(y, 2), round(bw, 2), round(bh, 2)],
                    "area": round(bw * bh, 2),
                    "iscrowd": 0,
                }
            )
            ann_id += 1
    return {
        "images": images,
        "annotations": annotations,
        "categories": [{"id": 1, "name": "item", "supercategory": "jewelry"}],
    }


def prepare(cfg: dict) -> Path:
    root = REPO / cfg["dataset_root"]
    coco = root / "coco"
    (coco / "annotations").mkdir(parents=True, exist_ok=True)
    for split, name in (("train", "train2017"), ("val", "val2017")):
        link = coco / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to((root / "images" / split).resolve(), target_is_directory=True)
        data = yolo_split_to_coco(root, split)
        (coco / "annotations" / f"instances_{name}.json").write_text(json.dumps(data))
        print(
            f"{split}: {len(data['images'])} images, {len(data['annotations'])} boxes"
        )
    return coco


# --------------------------------------------------------------------------- exp
def make_exp(cfg: dict, run_dir: Path):
    from yolox.exp import Exp

    preset = PRESETS[cfg["model"].replace("yolox_", "")]

    class TrayExp(Exp):
        def __init__(self) -> None:
            super().__init__()
            self.num_classes = 1
            self.depth, self.width = preset["depth"], preset["width"]
            self.depthwise = preset["depthwise"]
            self.input_size = tuple(cfg["input_size"])
            self.test_size = tuple(cfg["input_size"])
            self.max_epoch = int(cfg["epochs"])
            self.no_aug_epochs = int(cfg["no_aug_epochs"])
            self.warmup_epochs = int(cfg["warmup_epochs"])
            self.basic_lr_per_img = float(cfg["basic_lr_per_img"])
            self.mosaic_prob = float(cfg.get("mosaic_prob", 1.0))
            self.mixup_prob = float(cfg.get("mixup_prob", 1.0))
            self.eval_interval = int(cfg.get("eval_interval", 5))
            self.data_num_workers = int(cfg.get("num_workers", 2))
            self.seed = int(cfg["seed"])
            self.data_dir = str(REPO / cfg["dataset_root"] / "coco")
            self.output_dir = str(run_dir.parent)
            self.exp_name = run_dir.name
            if self.depthwise:
                self.mosaic_scale = (0.5, 1.5)
                self.enable_mixup = False

        def get_model(self):
            if getattr(self, "model", None) is None and self.depthwise:
                import torch.nn as nn
                from yolox.models import YOLOX, YOLOPAFPN, YOLOXHead

                in_channels = [256, 512, 1024]
                backbone = YOLOPAFPN(
                    self.depth, self.width, in_channels=in_channels, depthwise=True
                )
                head = YOLOXHead(
                    self.num_classes,
                    self.width,
                    in_channels=in_channels,
                    depthwise=True,
                )
                self.model = YOLOX(backbone, head)
                for m in self.model.modules():
                    if isinstance(m, nn.BatchNorm2d):
                        m.eps, m.momentum = 1e-3, 0.03
                self.model.head.initialize_biases(1e-2)
            return super().get_model()

    return TrayExp()


def _pretrained_state(cfg: dict, run_dir: Path):
    import torch

    url = cfg.get("pretrained")
    if not url:
        return None
    cache = REPO / "outputs" / "pretrained" / Path(url).name
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        torch.hub.download_url_to_file(url, str(cache))
    digest = hashlib.sha256(cache.read_bytes()).hexdigest()
    (run_dir / "pretrained.sha256").write_text(f"{digest}  {cache.name}\n")
    return torch.load(cache, map_location="cpu", weights_only=False)["model"]


# --------------------------------------------------------------------------- eval (val)
def predict_torch(model, img_bgr: np.ndarray, input_size, conf: float = 0.01):
    import torch
    from yolox.data.data_augment import ValTransform
    from yolox.utils import postprocess

    h, w = img_bgr.shape[:2]
    ratio = min(input_size[0] / h, input_size[1] / w)
    x, _ = ValTransform(legacy=False)(img_bgr, None, input_size)
    with torch.no_grad():
        out = model(torch.from_numpy(x).unsqueeze(0).float())
        out = postprocess(out, 1, conf, 0.45, class_agnostic=True)[0]
    if out is None:
        return []
    out = out.cpu().numpy()
    boxes = []
    for x1, y1, x2, y2, obj, cls, _ in out:
        boxes.append(
            (
                x1 / ratio,
                y1 / ratio,
                (x2 - x1) / ratio,
                (y2 - y1) / ratio,
                float(obj * cls),
            )
        )
    return boxes


def val_ap50(model, cfg: dict) -> float:
    import cv2

    root = REPO / cfg["dataset_root"]
    model.eval()
    model.head.decode_in_inference = True
    preds, gts = [], []
    for p in sorted((root / "images" / "val").iterdir()):
        if p.suffix.lower() not in IMAGE_EXTS:
            continue
        img = cv2.imread(str(p))
        h, w = img.shape[:2]
        preds.append(predict_torch(model, img, tuple(cfg["input_size"])))
        gts.append(read_yolo_labels(root / "labels" / "val" / f"{p.stem}.txt", w, h))
    model.train()
    return average_precision(preds, gts, 0.5) if gts else float("nan")


# --------------------------------------------------------------------------- train
def train_cpu(exp, cfg: dict, run_dir: Path, max_iters: int | None = None) -> Path:
    """Minimal single-process CPU loop over the official YOLOX Exp components."""
    import copy

    import torch
    from yolox.utils import ModelEMA, load_ckpt

    torch.set_num_threads(max(1, os.cpu_count() or 1))
    model = exp.get_model()
    state = _pretrained_state(cfg, run_dir)
    if state is not None:
        load_ckpt(model, state)  # skips the 80-class head tensors (shape mismatch)
    model.train()
    batch = int(cfg["batch_size"])
    loader = exp.get_data_loader(batch_size=batch, is_distributed=False, no_aug=False)
    optimizer = exp.get_optimizer(batch)
    iters_per_epoch = len(loader)
    lr_sched = exp.get_lr_scheduler(exp.basic_lr_per_img * batch, iters_per_epoch)
    ema = ModelEMA(model, 0.9998)
    it_loader = iter(loader)
    best_ap, best_path, last_path = -1.0, run_dir / "best.pth", run_dir / "last.pth"
    log = (run_dir / "train_log.jsonl").open("a")
    step = 0
    for epoch in range(exp.max_epoch):
        if epoch == exp.max_epoch - exp.no_aug_epochs:
            loader.close_mosaic()
            model.head.use_l1 = True
            it_loader = iter(loader)
        t0 = time.time()
        losses = []
        for _ in range(iters_per_epoch):
            inps, targets, _, _ = next(it_loader)
            inps, targets = exp.preprocess(
                inps.float(), targets.float(), exp.input_size
            )
            targets.requires_grad = False
            loss = model(inps, targets)["total_loss"]
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            ema.update(model)
            step += 1
            lr = lr_sched.update_lr(step)
            for g in optimizer.param_groups:
                g["lr"] = lr
            losses.append(float(loss))
            if max_iters is not None and step >= max_iters:
                break
        rec = {
            "epoch": epoch + 1,
            "loss": float(np.mean(losses)),
            "sec": round(time.time() - t0, 1),
        }
        last = (epoch + 1) % exp.eval_interval == 0 or epoch + 1 == exp.max_epoch
        if last or (max_iters is not None and step >= max_iters):
            ema_model = copy.deepcopy(ema.ema)
            rec["val_ap50"] = val_ap50(ema_model, cfg)
            ckpt = {
                "model": ema.ema.state_dict(),
                "epoch": epoch + 1,
                "val_ap50": rec["val_ap50"],
            }
            torch.save(ckpt, last_path)
            ap = (
                rec["val_ap50"] if rec["val_ap50"] == rec["val_ap50"] else -1
            )  # NaN -> -1
            if ap > best_ap:
                best_ap = ap
                torch.save(ckpt, best_path)
        log.write(json.dumps(rec) + "\n")
        log.flush()
        print(rec, flush=True)
        if max_iters is not None and step >= max_iters:
            break
    return best_path if best_path.exists() else last_path


def train_cuda(exp, cfg: dict, run_dir: Path) -> Path:  # pragma: no cover - needs a GPU
    from yolox.core import Trainer

    state = _pretrained_state(cfg, run_dir)
    ckpt = None
    if state is not None:
        ckpt = str(run_dir / "pretrained_model.pth")
        import torch

        torch.save({"model": state}, ckpt)
    args = SimpleNamespace(
        experiment_name=exp.exp_name,
        batch_size=int(cfg["batch_size"]),
        fp16=True,
        ckpt=ckpt,
        resume=False,
        start_epoch=None,
        occupy=False,
        cache=False,
        logger="tensorboard",
        opts=[],
    )
    Trainer(exp, args).train()
    return run_dir / "best_ckpt.pth"


def train(
    cfg: dict, device: str, run_name: str | None = None, max_iters: int | None = None
) -> Path:
    import torch

    run_dir = (
        REPO
        / cfg["output_dir"]
        / (run_name or datetime.now().strftime("%Y%m%d_%H%M%S"))
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.yaml").write_text(Path(cfg["_path"]).read_text())
    seed_everything(int(cfg["seed"]))
    exp = make_exp(cfg, run_dir)
    use_cuda = device == "cuda" or (device == "auto" and torch.cuda.is_available())
    return (
        train_cuda(exp, cfg, run_dir)
        if use_cuda
        else train_cpu(exp, cfg, run_dir, max_iters)
    )


# --------------------------------------------------------------------------- export
def export(cfg: dict, ckpt_path: Path, out_dir: Path | None = None) -> Path:
    import cv2
    import torch
    from torch import nn
    from yolox.models.network_blocks import SiLU
    from yolox.utils import replace_module

    out_dir = out_dir or (REPO / "models")
    out_dir.mkdir(parents=True, exist_ok=True)
    name = cfg["export"]["name"]
    exp = make_exp(cfg, REPO / cfg["output_dir"] / "export")
    model = exp.get_model()
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    model.load_state_dict(ckpt["model"])
    model.eval()
    model = replace_module(model, nn.SiLU, SiLU)
    model.head.decode_in_inference = False
    h, w = cfg["input_size"]
    onnx_path = out_dir / f"{name}.onnx"
    torch.onnx.export(
        model,
        torch.randn(1, 3, h, w),
        str(onnx_path),
        input_names=["images"],
        output_names=["output"],
        opset_version=int(cfg["export"]["opset"]),
        dynamo=False,
    )
    digest = hashlib.sha256(onnx_path.read_bytes()).hexdigest()
    sidecar = {
        "input_size": [h, w],
        "decode_in_model": False,
        "letterbox": "topleft",
        "pad_value": 114,
        "swap_rb": False,
        "strides": [8, 16, 32],
        "class_names": ["item"],
        "version": cfg["export"]["version"],
        "architecture": f"YOLOX-{cfg['model'].replace('yolox_', '')}",
        "framework": "YOLOX 0.3.0 (Apache-2.0)",
        "seed": cfg["seed"],
        "config_sha256": cfg["_sha256"],
        "checkpoint_epoch": ckpt.get("epoch"),
        "val_ap50": ckpt.get("val_ap50"),
        "sha256": digest,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out_dir / f"{name}.json").write_text(json.dumps(sidecar, indent=2) + "\n")
    (out_dir / f"{name}.sha256").write_text(f"{digest}  {name}.onnx\n")
    # The runtime path: OpenCV 5 must load the graph and produce YOLOX-shaped output.
    net = cv2.dnn.readNetFromONNX(str(onnx_path), cv2.dnn.ENGINE_AUTO)
    net.setInput(cv2.dnn.blobFromImage(np.zeros((h, w, 3), np.uint8)))
    out = net.forward()
    n_anchors = sum((h // s) * (w // s) for s in (8, 16, 32))
    assert out.shape[-2:] == (n_anchors, 6), out.shape
    print(
        f"exported {onnx_path} (sha256 {digest[:12]}…); cv2.dnn output {tuple(out.shape)}"
    )
    return onnx_path


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("cmd", choices=["prepare", "train", "export", "all"])
    ap.add_argument("--config", default="training/configs/yolox_trayagent.yaml")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--ckpt", default=None)
    ap.add_argument("--run-name", default=None)
    ap.add_argument(
        "--max-iters", type=int, default=None, help="stop early (smoke tests only)"
    )
    args = ap.parse_args()
    cfg = load_config(args.config)
    if args.cmd in ("prepare", "all"):
        prepare(cfg)
    ckpt = Path(args.ckpt) if args.ckpt else None
    if args.cmd in ("train", "all"):
        ckpt = train(cfg, args.device, args.run_name, args.max_iters)
        print(f"best checkpoint: {ckpt}")
    if args.cmd in ("export", "all"):
        if ckpt is None:
            raise SystemExit("--ckpt is required for export")
        export(cfg, ckpt)


if __name__ == "__main__":
    main()
