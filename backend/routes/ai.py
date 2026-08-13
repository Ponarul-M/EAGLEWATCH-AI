"""
routes/ai.py

Real AI detection API. Preserves backward compatibility with the
existing demo pipeline (routes/detection.py, POST /api/demo/detection)
- nothing here replaces it, this is purely additive.

    POST /api/ai/start    - start the background YOLO+ByteTrack worker
    POST /api/ai/stop     - stop it
    GET  /api/ai/status   - current worker status (fps, device, etc.)
    GET  /api/ai/stream   - MJPEG preview with bounding boxes
    POST /api/ai/detect   - one-shot detection on an uploaded image
                            (no temporal confirmation possible from a
                            single image - see detection_service docs)
"""

from __future__ import annotations

import logging
import time

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ai_config import config
from services.ai_worker import ai_worker
from services.detection_service import detection_service

logger = logging.getLogger("eaglewatch.ai.routes")

router = APIRouter(prefix="/api/ai", tags=["Real AI Detection"])


@router.post(
    "/start",
    summary="Start the real AI detection pipeline",
    description=(
        "Starts a background worker that reads frames from the "
        "configured VIDEO_SOURCE (webcam index or video file), runs "
        "YOLO detection + ByteTrack tracking, and creates incidents "
        "when the rule-based event analyzer confirms an event. "
        "Returns immediately; the worker keeps running in the background."
    ),
)
def start_ai(video_source: str | None = None, camera_id: str | None = None):
    result = ai_worker.start(video_source=video_source, camera_id=camera_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("detail"))
    return result


@router.post(
    "/stop",
    summary="Stop the real AI detection pipeline",
)
def stop_ai():
    return ai_worker.stop()


@router.get(
    "/status",
    summary="AI worker status",
    description="Reports whether the AI worker is running, its fps, "
                "device (cuda/cpu), model, and most recent detection - "
                "so the frontend can show a live 'AI Monitoring Active' indicator.",
)
def ai_status():
    return ai_worker.status()


@router.get(
    "/detections",
    summary="Live YOLO + ByteTrack detections for the current frame",
    description=(
        "Real, per-frame detections (track_id, class_name, confidence, "
        "bbox) plus the source frame's width/height, so the frontend "
        "can draw bounding boxes directly on top of the <video> element "
        "and scale them to however large it's displayed. Polled "
        "repeatedly by the Monitoring panel while the worker is running."
    ),
)
def ai_detections():
    return ai_worker.latest_detections()


@router.get(
    "/stream",
    summary="MJPEG preview stream with bounding boxes",
    description="Best-effort annotated video preview. If unavailable, "
                "prioritize /api/ai/status and incident creation instead "
                "(see project README, Priority 7).",
)
def ai_stream():
    if not ai_worker.running:
        raise HTTPException(status_code=409, detail="AI worker is not running. Call POST /api/ai/start first.")

    def generate():
        logger.info("[STREAM] Client connected, waiting for first frame...")
        boundary = b"--frame\r\n"
        poll_interval = 0.03  # seconds - avoids a hot busy-loop while waiting
        waited = 0.0
        startup_timeout = 15.0  # give YOLO's first (slow, CPU warm-up) inference room
        sent_first_frame = False

        while ai_worker.running:
            frame_bytes = ai_worker.latest_jpeg()
            if frame_bytes is None:
                if not sent_first_frame and waited >= startup_timeout:
                    logger.error(
                        f"[STREAM] No frame became available within {startup_timeout:.0f}s - "
                        f"closing stream so the frontend can fall back to the plain video."
                    )
                    return
                time.sleep(poll_interval)
                waited += poll_interval
                continue

            if not sent_first_frame:
                logger.info("[STREAM] First frame sent, streaming started")
                sent_first_frame = True

            yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            time.sleep(poll_interval)

        logger.info("[STREAM] Worker stopped, closing stream")

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.post(
    "/detect",
    summary="Run YOLO detection on a single uploaded image",
    description=(
        "Runs real YOLO object detection (no ByteTrack identity across "
        "calls, since each request is a fresh image) on an uploaded "
        "image and returns the raw detections. Useful for quickly "
        "verifying the model works without starting the full video "
        "worker. Does NOT create incidents - single-frame detections "
        "cannot be temporally confirmed (see event_analyzer.py)."
    ),
)
async def detect_single_image(file: UploadFile = File(...)):
    try:
        detection_service.load_model()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"YOLO model unavailable: {exc}")

    contents = await file.read()
    npimg = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode uploaded image")

    try:
        tracks = detection_service.detect_and_track(frame)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Detection failed: {exc}")

    return {
        "device": detection_service.device,
        "model": config.YOLO_MODEL,
        "detections": [t.to_dict() for t in tracks],
        "count": len(tracks),
    }
