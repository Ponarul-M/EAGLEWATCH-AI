"""
End-to-end API tests using FastAPI's TestClient. Confirms:
  - GET /api/ai/status always returns a well-shaped response
  - POST /api/ai/start / /api/ai/stop don't crash the app even when
    the model/camera are unavailable (graceful error handling)
  - The legacy demo endpoint (POST /api/demo/detection) still works
    and still flows through to GET /api/incidents (backward compatibility)
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_ai_status_endpoint_shape():
    resp = client.get("/api/ai/status")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("running", "camera_id", "frames_processed", "fps", "model", "device"):
        assert key in body


def test_ai_start_with_missing_model_returns_clean_error_not_crash():
    with patch("services.ai_worker.detection_service.load_model", side_effect=RuntimeError("model missing")):
        resp = client.post("/api/ai/start")
    assert resp.status_code == 500
    assert "model missing" in resp.json()["detail"]


def test_ai_stop_when_not_running_is_ok():
    resp = client.post("/api/ai/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_running"


def test_ai_stream_returns_409_when_not_running():
    resp = client.get("/api/ai/stream")
    assert resp.status_code == 409


def test_demo_detection_still_works_end_to_end():
    """Backward compatibility: the original demo pipeline must keep working."""
    resp = client.post("/api/demo/detection", json={"scenario": "collision"})
    assert resp.status_code == 201
    incident = resp.json()
    assert incident["status"] == "Detected"

    # New incident shows up through the existing /api/incidents contract
    list_resp = client.get("/api/incidents")
    assert list_resp.status_code == 200
    ids = [i["id"] for i in list_resp.json()["incidents"]]
    assert incident["id"] in ids

    # Existing frontend field contract is untouched
    for field in ("id", "category", "label", "sub", "location", "camera_id",
                  "confidence", "severity", "status", "x", "y", "time"):
        assert field in incident
