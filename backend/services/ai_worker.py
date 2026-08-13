"""
services/ai_worker.py

Orchestrates the real AI pipeline in a background thread so FastAPI's
request thread is never blocked processing video:

    FastAPI -> AI Worker -> OpenCV -> YOLO -> ByteTrack -> Event Analyzer -> Incident Service

Implements TWO layers of duplicate-incident prevention:

  1. Per-run dedup (primary rule for the demo): once ONE incident has
     been created during the current start()..stop() run, no further
     incidents are created until the worker is started again (e.g. for
     a new video). See `_incident_created_this_run`.
  2. Cooldown (secondary safeguard, EVENT_COOLDOWN_SECONDS): the same
     (camera_id, event_type) won't fire again within the cooldown
     window - useful if this worker is later pointed at a long-running
     live camera feed instead of a short demo clip.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

import cv2

from ai_config import config
from database import SessionLocal
from services import incident_service
from services.camera_service import VideoFileSource, create_camera_source
from services.detection_service import detection_service
from services.event_analyzer import event_analyzer
from services.risk_predictor import risk_predictor
from services.severity_service import compute_confidence, compute_severity
from services.tracking_service import tracking_history

logger = logging.getLogger("eaglewatch.ai.worker")
logging.basicConfig(level=logging.INFO, format="%(message)s")


class AIWorker:
    """
    Singleton-style worker (one instance created at module import,
    reused by routes/ai.py). Only one camera stream runs at a time in
    this hackathon build - `active_camera_id` distinguishes it from
    any future multi-camera extension.
    """

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self.running = False
        # "idle" | "starting" | "active" | "error" - drives the
        # "AI MONITORING: ..." indicator in the Monitoring panel.
        self.state = "idle"
        self.camera_id: Optional[str] = None
        self.video_source: Optional[str] = None
        self.frames_processed = 0
        self.fps = 0.0
        self.objects_tracked = 0
        self.last_detection: Optional[str] = None
        self.last_detection_time: Optional[datetime] = None
        self.start_error: Optional[str] = None

        # --- Stage 1: pre-accident risk prediction state (see
        # services/risk_predictor.py). Populated every frame; frozen
        # once an accident is confirmed (see _process_frame). ---
        self.risk_level: str = "NORMAL"
        self.risk_type: Optional[str] = None
        self.collision_probability: float = 0.0
        self.time_to_collision: Optional[float] = None
        self.risk_reason: str = ""
        self.risk_track_ids: List[int] = []

        self._latest_jpeg: Optional[bytes] = None
        # True once the FIRST annotated frame of the current run has
        # been encoded and stored - lets the frontend wait for a real
        # frame to exist before switching from the plain video file to
        # the live MJPEG stream (see routes/ai.py GET /api/ai/stream
        # and README "Fixing a black video feed").
        self._stream_ready = False
        self._latest_detections: List[dict] = []
        self._frame_width = 0
        self._frame_height = 0

        self._cooldowns: Dict[str, float] = {}  # f"{camera_id}:{event_type}" -> last-fired epoch time
        self._incident_created_this_run = False

    # -----------------------------------------------------------------
    # Public control API (called from routes/ai.py)
    # -----------------------------------------------------------------

    def start(self, video_source: Optional[str] = None, camera_id: Optional[str] = None) -> dict:
        with self._lock:
            if self.running:
                return {"status": "already_running", "camera_id": self.camera_id}

            source = video_source or config.VIDEO_SOURCE
            cam_id = camera_id or config.CAMERA_ID

            self.state = "starting"
            self.start_error = None
            self._stop_event.clear()
            self.frames_processed = 0
            self.fps = 0.0
            self.objects_tracked = 0
            self.last_detection = None
            self.last_detection_time = None
            self.camera_id = cam_id
            self.video_source = source
            self._latest_detections = []
            self._frame_width = 0
            self._frame_height = 0
            self._latest_jpeg = None
            self._stream_ready = False
            # New run (new video/camera source) -> reset the "one
            # incident per run" gate and any lingering cooldown state
            # from a previous run. See module docstring.
            self._incident_created_this_run = False
            self._cooldowns = {}

            # Reset Stage 1 risk state and the predictor's own
            # per-camera debounce/persistence memory - a new run must
            # start at NORMAL, not carry over a previous video's
            # in-progress "building risk" counters for this camera_id.
            self.risk_level = "NORMAL"
            self.risk_type = None
            self.collision_probability = 0.0
            self.time_to_collision = None
            self.risk_reason = ""
            self.risk_track_ids = []
            risk_predictor.reset(cam_id)

            try:
                detection_service.load_model()
            except Exception as exc:
                self.start_error = f"Failed to load YOLO model: {exc}"
                self.state = "error"
                logger.error(f"[AI] {self.start_error}")
                return {"status": "error", "detail": self.start_error}

            self._thread = threading.Thread(
                target=self._run, args=(source, cam_id), daemon=True
            )
            self.running = True
            self._thread.start()
            logger.info(f"[AI] Starting camera {cam_id} (source={source})")

            return {"status": "started", "camera_id": cam_id}

    def stop(self) -> dict:
        with self._lock:
            if not self.running:
                self.state = "idle"
                return {"status": "not_running"}
            self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=5.0)

        self.running = False
        self.state = "idle"
        logger.info("[AI] Stopped")
        return {"status": "stopped", "camera_id": self.camera_id}

    def status(self) -> dict:
        prediction_active = self.risk_level in ("MEDIUM_RISK", "HIGH_RISK", "CRITICAL_RISK")
        return {
            "running": self.running,
            "monitoring": self.running,  # alias matching the spec's suggested API shape
            "state": self.state,
            "stream_ready": self._stream_ready,
            "ai_mode": config.AI_MODE,
            "camera_id": self.camera_id,
            "video_source": self.video_source,
            "frames_processed": self.frames_processed,
            "fps": round(self.fps, 1),
            "objects_tracked": self.objects_tracked,
            "last_detection": self.last_detection,
            "last_detection_time": self.last_detection_time.isoformat() if self.last_detection_time else None,
            "incident_created_this_run": self._incident_created_this_run,
            "incident_confirmed": self._incident_created_this_run,  # alias, spec's field name
            # --- Stage 1: pre-accident risk prediction ---
            "risk_level": self.risk_level,
            "risk_type": self.risk_type,
            "prediction_active": prediction_active,
            "collision_probability": self.collision_probability,
            "time_to_collision": self.time_to_collision,
            "reason": self.risk_reason,
            "risk_track_ids": self.risk_track_ids,
            "device": detection_service.device if detection_service.is_ready else None,
            "model": config.YOLO_MODEL,
            "tracker": config.TRACKER_CONFIG,
            "model_ready": detection_service.is_ready,
            "model_load_error": detection_service.load_error,
            "start_error": self.start_error,
        }

    def latest_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._latest_jpeg

    def latest_detections(self) -> dict:
        """
        Real, live YOLO+ByteTrack detections for the current frame, plus
        the frame dimensions they were computed against - the frontend
        uses frame_width/frame_height to scale each bbox onto the
        displayed <video> element instead of trusting hardcoded pixels.
        """
        with self._lock:
            return {
                "running": self.running,
                "detections": list(self._latest_detections),
                "frame_width": self._frame_width,
                "frame_height": self._frame_height,
            }

    # -----------------------------------------------------------------
    # Worker loop
    # -----------------------------------------------------------------

    def _run(self, source: str, camera_id: str) -> None:
        camera = create_camera_source(source)
        try:
            camera.open()
        except Exception as exc:
            logger.error(f"[AI] Camera error: {exc}")
            self.start_error = str(exc)
            self.state = "error"
            self.running = False
            return

        logger.info("[AI] Tracking started")
        self.state = "active"
        tracking_history.clear(camera_id)

        frame_count = 0
        loop_start = time.time()
        min_frame_interval = 1.0 / config.TARGET_FPS if config.TARGET_FPS > 0 else 0.0

        try:
            while not self._stop_event.is_set():
                loop_iter_start = time.time()
                ok, frame = camera.read()

                if not ok or frame is None:
                    if isinstance(camera, VideoFileSource) and camera.loops:
                        camera.restart()
                        continue
                    logger.error("[AI] Lost camera/video input, stopping worker")
                    self.start_error = "Video source ended or became unavailable"
                    break

                if frame_count == 0:
                    logger.info("[VIDEO] Frame read successfully")

                try:
                    self._process_frame(camera_id, frame)
                except Exception as exc:
                    # A single bad frame should never crash the worker.
                    logger.error(f"[AI] Frame processing error (continuing): {exc}")

                frame_count += 1
                self.frames_processed += 1
                elapsed = time.time() - loop_start
                if elapsed > 0:
                    self.fps = frame_count / elapsed

                if frame_count == 1:
                    h, w = frame.shape[:2]
                    logger.info(f"[AI] Frame processed - shape {w}x{h}, objects={self.objects_tracked}")
                    logger.info(f"[AI] Risk state: {self.risk_level}")
                    logger.info(f"[STREAM] First annotated frame ready (stream_ready=True)")

                if frame_count % config.LOG_EVERY_N_FRAMES == 0:
                    logger.info(f"[AI] Frame {frame_count} (fps={self.fps:.1f}, objects={self.objects_tracked})")
                    if self.risk_type is not None and self.time_to_collision is not None:
                        logger.info(
                            f"[AI] Tracks {self.risk_track_ids} -> TTC: {self.time_to_collision:.1f}s "
                            f"Risk: {self.risk_level}"
                        )

                # Pace the loop so we don't spin faster than necessary.
                iter_elapsed = time.time() - loop_iter_start
                if min_frame_interval > iter_elapsed:
                    time.sleep(min_frame_interval - iter_elapsed)
        finally:
            camera.release()
            self.running = False
            self.state = "error" if self.start_error else "idle"

    def _process_frame(self, camera_id: str, frame) -> None:
        tracks = detection_service.detect_and_track(frame)
        history = tracking_history.update(camera_id, tracks)
        self.objects_tracked = tracking_history.active_object_count(camera_id)

        # --- Stage 1: PRE-ACCIDENT RISK PREDICTION ---
        # Purely informational - never creates an incident by itself.
        # Uses the same tracks/history Stage 2 uses, just asks a
        # different question ("are they converging?" vs "did it already
        # happen?"). See services/risk_predictor.py.
        assessment = risk_predictor.predict(camera_id, tracks, history)
        if not self._incident_created_this_run:
            # Once Stage 2 confirms an accident, freeze the risk fields
            # into ACCIDENT_CONFIRMED (below) instead of letting later
            # frames overwrite them back toward NORMAL.
            self.risk_level = assessment.risk_level
            self.risk_type = assessment.risk_type
            self.collision_probability = assessment.collision_probability
            self.time_to_collision = assessment.time_to_collision
            self.risk_reason = assessment.reason
            self.risk_track_ids = assessment.involved_track_ids

        self._render_preview(frame, tracks, assessment)
        self._update_live_detections(frame, tracks)

        # --- Stage 2: ACCIDENT CONFIRMATION (existing logic, unchanged) ---
        candidate = event_analyzer.analyze(camera_id, tracks, history)
        if candidate is None:
            return

        # --- Primary rule for this demo: ONE incident per video run ---
        if self._incident_created_this_run:
            return

        cooldown_key = f"{camera_id}:{candidate.event_type}"
        now = time.time()
        last_fired = self._cooldowns.get(cooldown_key)
        if last_fired is not None and (now - last_fired) < config.EVENT_COOLDOWN_SECONDS:
            # Same camera + same event type within the cooldown window:
            # treat as the same ongoing incident, don't create a duplicate.
            return

        logger.info(f"[AI] Potential {candidate.label.lower()} detected")
        logger.info("[AI] Event confirmed")
        logger.info("[AI] ACCIDENT CONFIRMED")
        logger.info("[AI] Creating incident...")

        severity = compute_severity(candidate.event_type, candidate.severity_features)
        confidence = compute_confidence(
            candidate.max_detection_confidence,
            confirm_frames=config.EVENT_CONFIRM_FRAMES,
            required_frames=config.EVENT_CONFIRM_FRAMES,
        )

        self._cooldowns[cooldown_key] = now
        self._incident_created_this_run = True
        self.last_detection = candidate.label
        self.last_detection_time = datetime.utcnow()

        # A prediction is NOT an incident, but once Stage 2 confirms one,
        # the risk state should reflect that finality rather than
        # whatever Stage 1 happened to compute this same frame.
        self.risk_level = "ACCIDENT_CONFIRMED"
        self.risk_type = candidate.event_type
        self.time_to_collision = None
        self.risk_reason = candidate.label

        self._create_incident(camera_id, candidate, severity, confidence)

    def _create_incident(self, camera_id: str, candidate, severity: str, confidence: int) -> None:
        db = SessionLocal()
        try:
            incident = incident_service.create_incident_from_ai(
                db,
                category=candidate.category,
                label=candidate.label,
                sub=candidate.sub,
                camera_id=camera_id,
                confidence=confidence,
                severity=severity,
            )
            logger.info(f"[AI] Incident created: {incident.id}")
        except Exception as exc:
            logger.error(f"[AI] Failed to create incident: {exc}")
        finally:
            db.close()

    def _render_preview(self, frame, tracks, assessment=None) -> None:
        """Draws bounding boxes + labels, plus (if given a risk
        assessment) TTC/risk overlay for any converging pairs, and
        stores a JPEG-encoded copy for GET /api/ai/stream. Kept
        best-effort - a rendering failure must never take down the
        detection loop."""
        try:
            annotated = frame.copy()
            tracks_by_id = {t.track_id: t for t in tracks}

            for t in tracks:
                x1, y1, x2, y2 = [int(v) for v in t.bbox]
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (36, 169, 242), 2)
                label = f"{t.class_name} #{t.track_id} {t.confidence:.2f}"
                cv2.putText(
                    annotated, label, (x1, max(0, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (36, 169, 242), 1, cv2.LINE_AA,
                )

            # Stage 1 overlay: a connecting line + TTC/risk label for
            # every currently-converging pair (not just the reported
            # "top" one), color-coded by how urgent it is. Kept simple
            # on purpose - see spec "Do not clutter the video".
            RISK_COLOR = {
                "MEDIUM_RISK": (60, 200, 255),   # amber (BGR)
                "HIGH_RISK": (0, 165, 255),      # orange
                "CRITICAL_RISK": (0, 0, 255),    # red
            }
            if assessment is not None:
                for cand in assessment.raw_candidates:
                    color = RISK_COLOR.get(cand.instantaneous_level)
                    if color is None or len(cand.involved_track_ids) != 2:
                        continue
                    ta = tracks_by_id.get(cand.involved_track_ids[0])
                    tb = tracks_by_id.get(cand.involved_track_ids[1])
                    if ta is None or tb is None:
                        continue
                    pa = (int(ta.center_x), int(ta.center_y))
                    pb = (int(tb.center_x), int(tb.center_y))
                    cv2.line(annotated, pa, pb, color, 1, cv2.LINE_AA)
                    mid = ((pa[0] + pb[0]) // 2, (pa[1] + pb[1]) // 2)
                    ttc_txt = f"TTC {cand.time_to_collision:.1f}s" if cand.time_to_collision is not None else "RISK"
                    cv2.putText(
                        annotated, f"{cand.instantaneous_level.replace('_RISK','')} {ttc_txt}",
                        (mid[0], max(0, mid[1] - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA,
                    )

            ok, buf = cv2.imencode(".jpg", annotated)
            if ok:
                with self._lock:
                    self._latest_jpeg = buf.tobytes()
                    self._stream_ready = True
        except Exception as exc:
            logger.debug(f"[AI] Preview render skipped: {exc}")

    def _update_live_detections(self, frame, tracks) -> None:
        """Stores the current frame's real YOLO+ByteTrack detections
        (track id, class, confidence, bbox) plus frame dimensions so
        the frontend can poll GET /api/ai/detections and draw live
        bounding boxes directly on top of the <video> element, scaled
        to whatever size it's displayed at."""
        h, w = frame.shape[:2]
        dets = [
            {
                "track_id": t.track_id,
                "class_name": t.class_name,
                "confidence": round(float(t.confidence), 3),
                "bbox": [round(float(v), 1) for v in t.bbox],
            }
            for t in tracks
        ]
        with self._lock:
            self._frame_width = w
            self._frame_height = h
            self._latest_detections = dets


# Module-level singleton used by routes/ai.py
ai_worker = AIWorker()
