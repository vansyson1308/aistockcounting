"""Detector lifecycle and the single-shot count used by the legacy routes.

Mock mode is explicit only. When the ONNX model is missing, the service is
*not ready*: ``predict`` raises ``DetectorUnavailable`` (HTTP 503) and
``/health`` reports ``detector.ready=false``. Nothing silently falls back to
fake boxes.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

import numpy as np

from app.core.config import Settings, get_settings
from app.core.metrics import inference_duration_seconds, model_loaded
from app.cv.imageio import as_image
from app.services.detector_cv import Det, Detector, DetectorStatus, build_detector

logger = logging.getLogger("app")


class DetectorUnavailable(RuntimeError):
    pass


def _resolve_backend(settings: Settings) -> str:
    if settings.mock_mode:
        return "mock"
    return settings.detector_backend


class InferenceService:
    _semaphore: asyncio.Semaphore | None = None
    _detector: Detector | None = None
    _status: DetectorStatus | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self.settings = get_settings()
        if InferenceService._semaphore is None:
            InferenceService._semaphore = asyncio.Semaphore(
                self.settings.inference_concurrency_limit
            )
        self.ensure_loaded(self.settings)

    @classmethod
    def ensure_loaded(cls, settings: Settings | None = None) -> None:
        if cls._status is not None:
            return
        settings = settings or get_settings()
        with cls._lock:
            if cls._status is not None:
                return
            detector, status = build_detector(
                _resolve_backend(settings),
                model_path=settings.model_onnx_path,
                meta_path=settings.model_meta_path or None,
                engine=settings.dnn_engine,
                score_thr=settings.confidence_threshold,
                nms_thr=settings.nms_threshold,
            )
            cls._detector, cls._status = detector, status
            model_loaded.set(1 if status.ready and status.backend == "onnx" else 0)

    @classmethod
    def reset(cls) -> None:
        """Forget the loaded detector (tests, hot reload)."""
        with cls._lock:
            cls._detector, cls._status = None, None

    @classmethod
    def set_detector(cls, detector: Detector, status: DetectorStatus) -> None:
        with cls._lock:
            cls._detector, cls._status = detector, status

    @classmethod
    def status(cls) -> dict[str, Any]:
        cls.ensure_loaded()
        assert cls._status is not None
        return cls._status.as_dict()

    @classmethod
    def is_model_loaded(cls) -> bool:
        return bool(cls._status and cls._status.ready and cls._status.backend == "onnx")

    @classmethod
    def detector(cls) -> Detector:
        cls.ensure_loaded()
        if cls._detector is None:
            reason = cls._status.reason if cls._status else "not initialised"
            raise DetectorUnavailable(reason)
        return cls._detector

    def detect_array(self, img: np.ndarray) -> list[Det]:
        return self.detector().detect(img)

    async def predict(self, image: bytes | np.ndarray) -> dict[str, Any]:
        detector = self.detector()
        assert InferenceService._semaphore is not None
        async with InferenceService._semaphore:
            start = time.perf_counter()
            img = as_image(image)
            dets = await asyncio.to_thread(detector.detect, img)
            duration = time.perf_counter() - start
        inference_duration_seconds.observe(duration)
        boxes = [d.as_dict() for d in dets]
        confidence_avg = (
            round(sum(b["conf"] for b in boxes) / len(boxes), 4) if boxes else 0.0
        )
        return {
            "detected_count": len(boxes),
            "boxes": boxes,
            "confidence_avg": confidence_avg,
            "mock_mode": detector.name == "mock",
            "detector_backend": detector.name,
            "processing_time_ms": int(duration * 1000),
            "model_version": (
                self.settings.model_version
                if detector.name == "onnx"
                else detector.version
            ),
        }
