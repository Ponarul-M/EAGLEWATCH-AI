"""
services/severity_service.py

Transparent, rule-based severity engine. No randomness - severity is
always derived from the same signals the event_analyzer already
computed (overlap, deceleration, elapsed time, number of objects).

    Critical  - multiple vehicles + high overlap/motion change, or a
                confirmed fall that has persisted a long time
    High      - two-wheeler fall, person fall, dangerous roadside activity
    Medium    - suspicious movement / minor abnormal event
"""

from __future__ import annotations

from typing import Literal

Severity = Literal["critical", "high", "medium"]


def compute_severity(event_type: str, features: dict) -> Severity:
    if event_type == "collision":
        overlap = features.get("overlap_iou", 0.0)
        decel = features.get("sudden_deceleration", False)
        objects_involved = features.get("objects_involved", 2)
        if objects_involved >= 2 and (overlap > 0.35 or decel):
            return "critical"
        return "high"

    if event_type == "two_wheeler":
        # A rider that overlaps with a vehicle/person AND stopped
        # suddenly is more likely to be a real fall than either signal
        # alone.
        if features.get("sudden_stop") and features.get("overlap_iou", 0.0) > 0:
            return "critical"
        return "high"

    if event_type == "fall":
        elapsed = features.get("elapsed_seconds", 0.0)
        # A person down for a long stretch is more concerning - they
        # may be trapped/unable to get up.
        return "critical" if elapsed >= 4.0 else "high"

    if event_type == "pursuit":
        return "medium"

    return "medium"


def compute_confidence(max_detection_confidence: float, confirm_frames: int, required_frames: int) -> int:
    """
    Combines the underlying model's detection confidence with how
    solidly the temporal confirmation held (never random, always
    derived from real signals). Clamped to [0, 100].
    """
    base = max_detection_confidence * 100.0
    # Small, bounded boost for events confirmed well past the minimum
    # required number of frames - more temporal evidence, more confidence.
    stability_boost = min(8.0, max(0, confirm_frames - required_frames) * 1.5)
    confidence = base + stability_boost
    return int(max(0, min(100, round(confidence))))
