"""
services/camera_service.py

Reusable camera/video input abstraction used by the AI worker.

    CameraSource
        ├── WebcamSource     (VIDEO_SOURCE="0", "1", ...)
        ├── VideoFileSource  (VIDEO_SOURCE="/path/to/video.mp4")
        └── (future) RTSPSource

No real CCTV camera is required - a webcam index or a local video file
both work identically for the hackathon demo.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger("eaglewatch.ai.camera")


class CameraSource(ABC):
    """Common interface every video input implements."""

    def __init__(self, source: str):
        self.source = source
        self._cap = None

    @abstractmethod
    def open(self) -> None:
        ...

    def _log_opened_properties(self) -> None:
        """Diagnostic logging so a black/broken feed is easy to debug
        from the backend console alone - see README 'Testing the video
        pipeline'."""
        import cv2

        if self._cap is None:
            return
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(f"[VIDEO] Capture opened: True")
        logger.info(f"[VIDEO] FPS: {fps:.1f}" if fps else "[VIDEO] FPS: unknown")
        logger.info(f"[VIDEO] Width: {width}")
        logger.info(f"[VIDEO] Height: {height}")

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self._cap is None:
            return False, None
        ok, frame = self._cap.read()
        return ok, frame if ok else None

    def is_opened(self) -> bool:
        return bool(self._cap is not None and self._cap.isOpened())

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def loops(self) -> bool:
        """Whether this source should restart automatically at EOF."""
        return False


class WebcamSource(CameraSource):
    def open(self) -> None:
        import cv2

        index = int(self.source)
        logger.info(f"[VIDEO] Source: webcam index {index}")
        self._cap = cv2.VideoCapture(index)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Could not open webcam at index {index}. "
                f"Check that a camera is connected and not in use by "
                f"another application."
            )
        self._log_opened_properties()


class VideoFileSource(CameraSource):
    def open(self) -> None:
        import cv2

        abs_path = os.path.abspath(self.source)
        exists = os.path.exists(self.source)
        logger.info(f"[VIDEO] Source: {self.source}")
        logger.info(f"[VIDEO] Absolute path: {abs_path}")
        logger.info(f"[VIDEO] Exists: {exists}")

        if not exists:
            raise RuntimeError(
                f"Video file not found: {self.source} (resolved to {abs_path}). "
                f"Check the path is relative to the backend/ working directory "
                f"uvicorn was started from, e.g. 'sample_video/car_accident.mp4'."
            )

        self._cap = cv2.VideoCapture(self.source)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Could not open video file: {self.source} "
                f"(unsupported codec or corrupt file?)"
            )
        self._log_opened_properties()

    @property
    def loops(self) -> bool:
        # Loop sample/demo videos so a hackathon demo can run indefinitely.
        return True

    def restart(self) -> None:
        import cv2

        if self._cap is not None:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)


def create_camera_source(video_source: str) -> CameraSource:
    """
    Factory: "0", "1", ... -> WebcamSource
             anything else  -> VideoFileSource
    """
    video_source = str(video_source).strip()
    if video_source.isdigit():
        return WebcamSource(video_source)
    return VideoFileSource(video_source)
