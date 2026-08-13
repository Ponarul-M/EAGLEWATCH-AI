"""
services/detection_service.py

Real AI detection layer.

This module is responsible ONLY for:
  - loading the YOLO model (Ultralytics)
  - running YOLO detection + ByteTrack tracking on a single frame
  - returning a plain list of tracked-object dicts

It does NOT decide what counts as an "incident" - that reasoning lives
in event_analyzer.py (temporal, rule-based logic) and severity_service.py.
This separation is deliberate: YOLO/ByteTrack tell us *what objects are
where*, not *whether something bad is happening*.

Honesty note (see README "AI Pipeline" section):
    - Object detection (YOLO) and tracking (ByteTrack) are real ML/CV.
    - "Vehicle Collision", "Person Distress", etc. are rule-based
      interpretations of tracked-object motion over time, not something
      YOLO itself understands.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional

import numpy as np

from ai_config import config

logger = logging.getLogger("eaglewatch.ai.detection")


@dataclass
class TrackedObject:
    track_id: int
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple  # (x1, y1, x2, y2)
    center_x: float
    center_y: float
    timestamp: float = field(default_factory=time.time)

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "center_x": self.center_x,
            "center_y": self.center_y,
            "timestamp": self.timestamp,
        }


# Classes (COCO) relevant to EagleWatch's demo scenarios. Everything
# else YOLO detects is still tracked, but the event analyzer only
# reasons about these.
VEHICLE_CLASSES = {"car", "truck", "bus", "train"}
TWO_WHEELER_CLASSES = {"motorcycle", "bicycle"}
PERSON_CLASS = "person"


class DetectionService:
    """
    Lazily loads a single YOLO model instance and exposes tracked
    detections for one frame at a time.
    """

    def __init__(self):
        self._model = None
        self._device = None
        self._load_error: Optional[str] = None

    # -----------------------------------------------------------------
    # Model loading
    # -----------------------------------------------------------------

    def _resolve_device(self) -> str:
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:  # torch not installed / no CUDA build
            return "cpu"

    def load_model(self) -> None:
        if self._model is not None:
            return

        logger.info("[AI] Loading YOLO model...")
        self._device = self._resolve_device()

        try:
            from ultralytics import YOLO

            self._model = YOLO(config.YOLO_MODEL)
            logger.info("[AI] Model loaded successfully")
            logger.info(f"[AI] Device: {self._device.upper()}")
            self._load_error = None
        except Exception as exc:
            self._model = None
            self._load_error = str(exc)
            logger.error(f"[AI] Failed to load YOLO model '{config.YOLO_MODEL}': {exc}")
            raise

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    @property
    def device(self) -> str:
        return self._device or self._resolve_device()

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    # -----------------------------------------------------------------
    # Inference
    # -----------------------------------------------------------------

    def detect_and_track(self, frame: np.ndarray) -> List[TrackedObject]:
        """
        Runs YOLO detection + ByteTrack tracking on a single BGR frame.
        Returns a list of TrackedObject. Never raises for "no
        detections" - only for a genuinely broken model/frame.
        """
        if self._model is None:
            raise RuntimeError("YOLO model is not loaded. Call load_model() first.")

        device_arg = 0 if self.device == "cuda" else "cpu"

        results = self._model.track(
            frame,
            persist=True,
            tracker=config.TRACKER_CONFIG,
            conf=config.CONFIDENCE_THRESHOLD,
            device=device_arg,
            verbose=False,
        )

        tracked: List[TrackedObject] = []
        if not results:
            return tracked

        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or boxes.id is None:
            # Detections with no assigned track id (e.g. first frame of
            # a new object) are skipped - the event analyzer needs
            # persistent ids to reason over time anyway.
            return tracked

        names = result.names
        now = time.time()

        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        cls_ids = boxes.cls.cpu().numpy().astype(int)
        track_ids = boxes.id.cpu().numpy().astype(int)

        for i in range(len(track_ids)):
            x1, y1, x2, y2 = [float(v) for v in xyxy[i]]
            cls_id = int(cls_ids[i])
            class_name = names.get(cls_id, str(cls_id)) if isinstance(names, dict) else str(cls_id)

            tracked.append(
                TrackedObject(
                    track_id=int(track_ids[i]),
                    class_id=cls_id,
                    class_name=class_name,
                    confidence=float(confs[i]),
                    bbox=(x1, y1, x2, y2),
                    center_x=(x1 + x2) / 2.0,
                    center_y=(y1 + y2) / 2.0,
                    timestamp=now,
                )
            )

        return tracked


# Module-level singleton - one model instance shared by the whole app.
detection_service = DetectionService()


def detect_event(frame: Optional[Any] = None, camera_id: Optional[str] = None):
    """
    Kept for backward compatibility with the original placeholder
    signature. Prefer `detection_service.detect_and_track()` plus
    `event_analyzer` for real usage - a single frame alone is never
    enough to confirm an incident (see AI pipeline docs).
    """
    raise NotImplementedError(
        "detect_event() operates on a single frame and cannot confirm "
        "incidents by itself. Use the AI worker (POST /api/ai/start), "
        "which runs detection_service + tracking_service + "
        "event_analyzer together across frames."
    )
