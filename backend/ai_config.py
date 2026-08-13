"""
ai_config.py

Single source of truth for all AI-pipeline configuration.
Everything here is read from environment variables (.env) so nothing
about the AI pipeline is hardcoded elsewhere in the codebase.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class AIConfig:
    # "real"  -> YOLO + ByteTrack pipeline
    # "demo"  -> canned scenario system (services/incident_service.SCENARIOS)
    AI_MODE: str = os.getenv("AI_MODE", "demo").strip().lower()

    # YOLO / tracking
    YOLO_MODEL: str = os.getenv("YOLO_MODEL", "yolo11n.pt")
    CONFIDENCE_THRESHOLD: float = _get_float("CONFIDENCE_THRESHOLD", 0.40)
    TRACKER_CONFIG: str = os.getenv("TRACKER_CONFIG", "bytetrack.yaml")

    # How many recent (timestamp, cx, cy, w, h) points to keep per track_id
    TRACK_HISTORY_LENGTH: int = _get_int("TRACK_HISTORY_LENGTH", 60)

    # Consecutive confirming frames required before an event fires
    EVENT_CONFIRM_FRAMES: int = _get_int("EVENT_CONFIRM_FRAMES", 5)

    # Duplicate-incident suppression window
    EVENT_COOLDOWN_SECONDS: int = _get_int("EVENT_COOLDOWN_SECONDS", 30)

    # --- Pre-accident risk prediction (services/risk_predictor.py) ---
    # Consecutive confirming frames required before a risk level is
    # reported as sustained (same debouncing idea as EVENT_CONFIRM_FRAMES,
    # but a separate, usually-shorter knob: we WANT the warning to show
    # up earlier than the accident-confirmation event does).
    RISK_CONFIRM_FRAMES: int = _get_int("RISK_CONFIRM_FRAMES", 4)
    # How far into the future (seconds) a projected closest-approach is
    # still considered a meaningful warning. Longer than this and it's
    # too speculative to call it a "risk".
    TTC_HORIZON_SECONDS: float = _get_float("TTC_HORIZON_SECONDS", 4.0)
    # Projected closest-approach distance (pixels) below which two
    # objects are considered on a collision course. This is in image
    # pixel space, so it implicitly depends on camera distance/zoom -
    # tune per camera. See README "Limitations".
    COLLISION_DISTANCE_PX: float = _get_float("COLLISION_DISTANCE_PX", 80.0)
    # Minimum closing speed (px/s) before two objects are even
    # considered "approaching" - filters out near-stationary noise.
    MIN_CLOSING_SPEED_PX_S: float = _get_float("MIN_CLOSING_SPEED_PX_S", 15.0)

    # Camera / video source
    VIDEO_SOURCE: str = os.getenv("VIDEO_SOURCE", "0")
    CAMERA_ID: str = os.getenv("CAMERA_ID", "CAM-01")
    CAMERA_LOCATION: str = os.getenv("CAMERA_LOCATION", "Anna Salai & Mount Road")
    CAMERA_X: float = _get_float("CAMERA_X", 50.0)
    CAMERA_Y: float = _get_float("CAMERA_Y", 50.0)

    # Worker loop
    TARGET_FPS: float = _get_float("AI_TARGET_FPS", 12.0)
    LOG_EVERY_N_FRAMES: int = _get_int("AI_LOG_EVERY_N_FRAMES", 150)

    @classmethod
    def as_dict(cls) -> dict:
        return {
            "ai_mode": cls.AI_MODE,
            "yolo_model": cls.YOLO_MODEL,
            "confidence_threshold": cls.CONFIDENCE_THRESHOLD,
            "tracker_config": cls.TRACKER_CONFIG,
            "event_confirm_frames": cls.EVENT_CONFIRM_FRAMES,
            "event_cooldown_seconds": cls.EVENT_COOLDOWN_SECONDS,
            "video_source": cls.VIDEO_SOURCE,
            "camera_id": cls.CAMERA_ID,
            "camera_location": cls.CAMERA_LOCATION,
        }


config = AIConfig()
