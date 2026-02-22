import asyncio
import hashlib
import io
import logging
import time
from pathlib import Path
from typing import Any

from PIL import Image

from app.core.config import get_settings

logger = logging.getLogger("app")


class InferenceService:
    _semaphore: asyncio.Semaphore | None = None

    def __init__(self) -> None:
        self.settings = get_settings()
        if InferenceService._semaphore is None:
            InferenceService._semaphore = asyncio.Semaphore(
                self.settings.inference_concurrency_limit
            )

        self.onnx_path = Path(self.settings.model_onnx_path)
        self.pt_path = Path(self.settings.model_pt_path)
        # backward compatibility
        if not self.onnx_path.exists() and Path(self.settings.model_path).exists():
            self.onnx_path = Path(self.settings.model_path)

    async def predict(self, image_bytes: bytes) -> dict[str, Any]:
        assert InferenceService._semaphore is not None
        async with InferenceService._semaphore:
            start = time.perf_counter()

            if self.settings.mock_mode:
                payload = self._mock_predict(image_bytes)
            else:
                payload = self._predict_real_or_fallback(image_bytes)

            payload["processing_time_ms"] = int((time.perf_counter() - start) * 1000)
            return payload

    def _predict_real_or_fallback(self, image_bytes: bytes) -> dict[str, Any]:
        if self.onnx_path.exists():
            return self._run_yolo(str(self.onnx_path), image_bytes)
        if self.pt_path.exists():
            return self._run_yolo(str(self.pt_path), image_bytes)

        logger.warning(
            "No MODEL_ONNX_PATH/MODEL_PT_PATH found; fallback to MOCK_MODE behavior"
        )
        return self._mock_predict(image_bytes)

    def _run_yolo(self, model_path: str, image_bytes: bytes) -> dict[str, Any]:
        try:
            from ultralytics import YOLO
        except Exception:
            logger.warning("Ultralytics unavailable; fallback to MOCK_MODE behavior")
            return self._mock_predict(image_bytes)

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        model = YOLO(model_path)
        result = model.predict(
            image, conf=self.settings.confidence_threshold, verbose=False
        )[0]

        boxes: list[dict[str, float]] = []
        confidences: list[float] = []
        for box in result.boxes:
            xyxy = box.xyxy[0].tolist()
            conf = float(box.conf[0].item())
            x1, y1, x2, y2 = xyxy
            boxes.append(
                {
                    "x": float(x1),
                    "y": float(y1),
                    "w": float(max(x2 - x1, 0.0)),
                    "h": float(max(y2 - y1, 0.0)),
                    "conf": round(conf, 4),
                }
            )
            confidences.append(conf)

        confidence_avg = (
            round(sum(confidences) / len(confidences), 4) if confidences else 0.0
        )
        return {
            "detected_count": len(boxes),
            "boxes": boxes,
            "confidence_avg": confidence_avg,
        }

    def _mock_predict(self, image_bytes: bytes) -> dict[str, Any]:
        seed = int(hashlib.sha256(image_bytes).hexdigest()[:8], 16)
        count = (seed % 4) + 2
        boxes: list[dict[str, float]] = []
        for idx in range(count):
            boxes.append(
                {
                    "x": float(20 + idx * 35),
                    "y": float(25 + idx * 20),
                    "w": 40.0,
                    "h": 30.0,
                    "conf": round(0.75 + (idx * 0.03), 2),
                }
            )
        confidence_avg = round(sum(b["conf"] for b in boxes) / len(boxes), 4)
        return {
            "detected_count": len(boxes),
            "boxes": boxes,
            "confidence_avg": confidence_avg,
        }
