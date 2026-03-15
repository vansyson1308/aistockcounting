import asyncio
import hashlib
import io
import logging
import time
from pathlib import Path
from typing import Any

from PIL import Image

from app.core.config import get_settings
from app.core.metrics import inference_duration_seconds, model_loaded

logger = logging.getLogger("app")


class InferenceService:
    _semaphore: asyncio.Semaphore | None = None
    _model: Any = None
    _model_path: str | None = None
    _model_loaded: bool = False

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

        # Load model once (singleton)
        if not self.settings.mock_mode and InferenceService._model is None:
            self._load_model()

    def _load_model(self) -> None:
        """Load YOLO model once at startup."""
        model_path: str | None = None
        if self.onnx_path.exists():
            model_path = str(self.onnx_path)
        elif self.pt_path.exists():
            model_path = str(self.pt_path)

        if model_path is None:
            logger.warning(
                "No MODEL_ONNX_PATH/MODEL_PT_PATH found; will use MOCK_MODE behavior"
            )
            return

        try:
            from ultralytics import YOLO

            InferenceService._model = YOLO(model_path)
            InferenceService._model_path = model_path
            InferenceService._model_loaded = True
            model_loaded.set(1)
            logger.info("Model loaded: %s", model_path)
        except Exception:
            logger.warning("Ultralytics unavailable; will use MOCK_MODE behavior")

    @classmethod
    def is_model_loaded(cls) -> bool:
        return cls._model_loaded

    async def predict(self, image_bytes: bytes) -> dict[str, Any]:
        assert InferenceService._semaphore is not None
        async with InferenceService._semaphore:
            start = time.perf_counter()

            if self.settings.mock_mode:
                payload = self._mock_predict(image_bytes)
                payload["mock_mode"] = True
            elif InferenceService._model is not None:
                payload = self._run_yolo(image_bytes)
                payload["mock_mode"] = False
            else:
                # No model available, fallback to mock
                logger.warning("No model loaded; falling back to mock prediction")
                payload = self._mock_predict(image_bytes)
                payload["mock_mode"] = True

            duration = time.perf_counter() - start
            inference_duration_seconds.observe(duration)
            payload["processing_time_ms"] = int(duration * 1000)
            payload["model_version"] = self.settings.model_version
            return payload

    def _run_yolo(self, image_bytes: bytes) -> dict[str, Any]:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        result = InferenceService._model.predict(
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
