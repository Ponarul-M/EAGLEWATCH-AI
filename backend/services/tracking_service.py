"""
services/tracking_service.py

Maintains short-term movement history per ByteTrack track_id, e.g.:

    track_history = {
        track_id: [
            (timestamp, center_x, center_y, width, height, class_name, confidence),
            ...
        ]
    }

History length is capped (ai_config.TRACK_HISTORY_LENGTH) so memory
stays small even for long-running streams. Stale tracks (not seen for
a while) are pruned each frame so memory doesn't grow unbounded when
objects leave the frame.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Dict, List, NamedTuple

from ai_config import config
from services.detection_service import TrackedObject

# A track is considered stale (object left the scene) if we haven't
# seen it for this many seconds.
STALE_TRACK_SECONDS = 5.0


class HistoryPoint(NamedTuple):
    timestamp: float
    center_x: float
    center_y: float
    width: float
    height: float
    class_name: str
    confidence: float


class TrackingHistory:
    """Per-camera track history store."""

    def __init__(self):
        # camera_id -> { track_id -> deque[HistoryPoint] }
        self._history: Dict[str, Dict[int, deque]] = {}

    def update(self, camera_id: str, tracks: List[TrackedObject]) -> Dict[int, List[HistoryPoint]]:
        cam_history = self._history.setdefault(camera_id, {})
        seen_ids = set()

        for t in tracks:
            seen_ids.add(t.track_id)
            dq = cam_history.setdefault(t.track_id, deque(maxlen=config.TRACK_HISTORY_LENGTH))
            dq.append(
                HistoryPoint(
                    timestamp=t.timestamp,
                    center_x=t.center_x,
                    center_y=t.center_y,
                    width=t.width,
                    height=t.height,
                    class_name=t.class_name,
                    confidence=t.confidence,
                )
            )

        self._prune_stale(cam_history)
        return {tid: list(dq) for tid, dq in cam_history.items()}

    def _prune_stale(self, cam_history: Dict[int, deque]) -> None:
        now = time.time()
        stale_ids = [
            tid for tid, dq in cam_history.items()
            if dq and (now - dq[-1].timestamp) > STALE_TRACK_SECONDS
        ]
        for tid in stale_ids:
            del cam_history[tid]

    def get(self, camera_id: str) -> Dict[int, List[HistoryPoint]]:
        return {tid: list(dq) for tid, dq in self._history.get(camera_id, {}).items()}

    def clear(self, camera_id: str) -> None:
        self._history.pop(camera_id, None)

    def active_object_count(self, camera_id: str) -> int:
        return len(self._history.get(camera_id, {}))


# Module-level singleton shared by the AI worker.
tracking_history = TrackingHistory()
