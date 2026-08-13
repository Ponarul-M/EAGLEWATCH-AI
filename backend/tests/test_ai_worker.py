"""
Tests the AI worker's duplicate-incident prevention (the primary
per-video-run gate + the secondary cooldown safeguard) and its
start/stop lifecycle, without a real camera or GPU: detection_service
and the camera are monkeypatched.
"""

from unittest.mock import MagicMock, patch

import numpy as np

from services.ai_worker import AIWorker
from services.event_analyzer import EventCandidate


def _fake_candidate():
    return EventCandidate(
        event_type="collision",
        category="accident",
        label="Vehicle Collision",
        sub="Possible multi-vehicle collision detected",
        severity_features={"objects_involved": 2, "overlap_iou": 0.5, "sudden_deceleration": True},
        object_track_ids=[1, 2],
        max_detection_confidence=0.9,
    )


def test_cooldown_prevents_duplicate_incidents_within_window():
    worker = AIWorker()
    created_incidents = []

    with patch("services.ai_worker.detection_service.detect_and_track", return_value=[]), \
         patch("services.ai_worker.tracking_history.update", return_value={}), \
         patch("services.ai_worker.tracking_history.active_object_count", return_value=2), \
         patch("services.ai_worker.event_analyzer.analyze", return_value=_fake_candidate()), \
         patch.object(worker, "_create_incident", side_effect=lambda *a, **k: created_incidents.append(a)), \
         patch.object(worker, "_render_preview", return_value=None):

        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        worker._process_frame("CAM-01", frame)
        worker._process_frame("CAM-01", frame)  # same event, within cooldown
        worker._process_frame("CAM-01", frame)  # still within cooldown

    assert len(created_incidents) == 1  # deduplicated, not 3 incidents


def test_one_incident_per_run_even_after_cooldown_window_expires():
    """
    Primary rule for the demo: exactly ONE incident per video run,
    regardless of how long the video is or how many times the cooldown
    window would otherwise have reset.
    """
    worker = AIWorker()
    created_incidents = []

    with patch("services.ai_worker.detection_service.detect_and_track", return_value=[]), \
         patch("services.ai_worker.tracking_history.update", return_value={}), \
         patch("services.ai_worker.tracking_history.active_object_count", return_value=2), \
         patch("services.ai_worker.event_analyzer.analyze", return_value=_fake_candidate()), \
         patch.object(worker, "_create_incident", side_effect=lambda *a, **k: created_incidents.append(a)), \
         patch.object(worker, "_render_preview", return_value=None):

        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        worker._process_frame("CAM-01", frame)
        assert worker._incident_created_this_run is True

        # Even if the cooldown window has fully elapsed, the same run
        # must not create a second incident.
        for key in list(worker._cooldowns.keys()):
            worker._cooldowns[key] -= 9999
        worker._process_frame("CAM-01", frame)
        worker._process_frame("CAM-01", frame)

    assert len(created_incidents) == 1


def test_starting_a_new_run_resets_the_per_run_dedup_gate():
    """Selecting a new video (a fresh start()) must allow a new incident."""
    worker = AIWorker()
    created_incidents = []

    with patch("services.ai_worker.detection_service.detect_and_track", return_value=[]), \
         patch("services.ai_worker.tracking_history.update", return_value={}), \
         patch("services.ai_worker.tracking_history.active_object_count", return_value=2), \
         patch("services.ai_worker.event_analyzer.analyze", return_value=_fake_candidate()), \
         patch.object(worker, "_create_incident", side_effect=lambda *a, **k: created_incidents.append(a)), \
         patch.object(worker, "_render_preview", return_value=None):

        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        worker._process_frame("CAM-01", frame)
        assert len(created_incidents) == 1

        # Simulate the user picking a new scenario/video: a fresh
        # start() must reset the dedup gate for the new run.
        with patch("services.ai_worker.detection_service.load_model", return_value=None), \
             patch.object(worker, "_run", return_value=None):
            worker.start(video_source="sample_video/two_wheeler_accident.mp4", camera_id="CAM-01")
        assert worker._incident_created_this_run is False

        worker._process_frame("CAM-01", frame)

    assert len(created_incidents) == 2


def test_stream_becomes_ready_only_after_a_real_frame_is_rendered():
    """Reproduces the black-screen bug directly: stream_ready must be
    False the instant the worker starts (thread launched, no frame yet)
    and only flip True once _render_preview has actually encoded and
    stored a JPEG - this is what the frontend now waits on before
    swapping from the plain video file to the live MJPEG stream."""
    worker = AIWorker()
    assert worker.status()["stream_ready"] is False

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    fake_track = MagicMock()
    fake_track.track_id = 1
    fake_track.class_name = "car"
    fake_track.confidence = 0.9
    fake_track.bbox = (0.0, 0.0, 20.0, 20.0)

    # Real (unmocked) _render_preview - this is the exact code path
    # that must set stream_ready once a frame is actually encoded.
    worker._render_preview(frame, [fake_track], assessment=None)
    assert worker.latest_jpeg() is not None
    assert worker.status()["stream_ready"] is True


def test_stream_ready_resets_on_a_new_start():
    worker = AIWorker()
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    worker._render_preview(frame, [], assessment=None)
    assert worker.status()["stream_ready"] is True

    with patch("services.ai_worker.detection_service.load_model", return_value=None), \
         patch.object(worker, "_run", return_value=None):
        worker.start(video_source="sample_video/x.mp4", camera_id="CAM-01")

    assert worker.status()["stream_ready"] is False
    assert worker.latest_jpeg() is None
    worker.stop()


def test_live_detections_reflect_current_frame():
    worker = AIWorker()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    fake_track = MagicMock()
    fake_track.track_id = 12
    fake_track.class_name = "car"
    fake_track.confidence = 0.91
    fake_track.bbox = (10.0, 20.0, 110.0, 220.0)

    with patch("services.ai_worker.detection_service.detect_and_track", return_value=[fake_track]), \
         patch("services.ai_worker.tracking_history.update", return_value={}), \
         patch("services.ai_worker.tracking_history.active_object_count", return_value=1), \
         patch("services.ai_worker.event_analyzer.analyze", return_value=None), \
         patch.object(worker, "_render_preview", return_value=None):
        worker._process_frame("CAM-01", frame)

    data = worker.latest_detections()
    assert data["frame_width"] == 640
    assert data["frame_height"] == 480
    assert len(data["detections"]) == 1
    det = data["detections"][0]
    assert det["track_id"] == 12
    assert det["class_name"] == "car"
    assert det["bbox"] == [10.0, 20.0, 110.0, 220.0]


def test_start_reports_model_load_failure_without_crashing():
    worker = AIWorker()
    with patch("services.ai_worker.detection_service.load_model", side_effect=RuntimeError("no model file")):
        result = worker.start(video_source="0", camera_id="CAM-01")

    assert result["status"] == "error"
    assert worker.running is False
    assert worker.state == "error"


def test_start_twice_reports_already_running():
    worker = AIWorker()
    with patch("services.ai_worker.detection_service.load_model", return_value=None), \
         patch.object(worker, "_run", return_value=None):
        first = worker.start(video_source="0", camera_id="CAM-01")
        assert first["status"] == "started"
        second = worker.start(video_source="0", camera_id="CAM-01")
        assert second["status"] == "already_running"
    worker.stop()


def test_stop_when_not_running_is_safe():
    worker = AIWorker()
    result = worker.stop()
    assert result["status"] == "not_running"
    assert worker.state == "idle"


def test_status_shape():
    worker = AIWorker()
    status = worker.status()
    for key in ("running", "monitoring", "state", "stream_ready", "camera_id", "video_source", "frames_processed", "fps",
                "objects_tracked", "last_detection", "last_detection_time",
                "incident_created_this_run", "incident_confirmed", "device", "model",
                "risk_level", "risk_type", "prediction_active", "collision_probability",
                "time_to_collision", "reason"):
        assert key in status
    assert status["risk_level"] == "NORMAL"
    assert status["prediction_active"] is False


def test_risk_fields_populate_and_freeze_on_accident_confirmation():
    worker = AIWorker()
    created_incidents = []

    from services.risk_predictor import RiskAssessment

    fake_assessment = RiskAssessment(
        risk_level="HIGH_RISK", risk_type="vehicle_collision",
        collision_probability=0.8, time_to_collision=1.2,
        reason="Converging trajectories", involved_track_ids=[1, 2],
    )

    with patch("services.ai_worker.detection_service.detect_and_track", return_value=[]), \
         patch("services.ai_worker.tracking_history.update", return_value={}), \
         patch("services.ai_worker.tracking_history.active_object_count", return_value=2), \
         patch("services.ai_worker.risk_predictor.predict", return_value=fake_assessment), \
         patch("services.ai_worker.event_analyzer.analyze", return_value=None), \
         patch.object(worker, "_render_preview", return_value=None):
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        worker._process_frame("CAM-01", frame)

    assert worker.risk_level == "HIGH_RISK"
    assert worker.status()["prediction_active"] is True
    assert worker.status()["incident_confirmed"] is False

    # Now Stage 2 confirms - risk state must freeze to ACCIDENT_CONFIRMED
    # instead of whatever Stage 1 reports on this same frame.
    with patch("services.ai_worker.detection_service.detect_and_track", return_value=[]), \
         patch("services.ai_worker.tracking_history.update", return_value={}), \
         patch("services.ai_worker.tracking_history.active_object_count", return_value=2), \
         patch("services.ai_worker.risk_predictor.predict", return_value=fake_assessment), \
         patch("services.ai_worker.event_analyzer.analyze", return_value=_fake_candidate()), \
         patch.object(worker, "_create_incident", side_effect=lambda *a, **k: created_incidents.append(a)), \
         patch.object(worker, "_render_preview", return_value=None):
        worker._process_frame("CAM-01", frame)

    assert worker.risk_level == "ACCIDENT_CONFIRMED"
    assert worker.status()["incident_confirmed"] is True
    assert len(created_incidents) == 1
