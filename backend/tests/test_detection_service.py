"""
Mocks Ultralytics so these tests run without downloading a real model
or needing a GPU. Verifies:
  1. Model loading (success + failure paths)
  2. Detection output structure (TrackedObject fields)
"""

import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pytest

from services.detection_service import DetectionService


def _install_fake_ultralytics(monkeypatch, track_return):
    fake_module = types.ModuleType("ultralytics")

    class FakeYOLO:
        def __init__(self, model_path):
            self.model_path = model_path

        def track(self, *args, **kwargs):
            return track_return

    fake_module.YOLO = FakeYOLO
    monkeypatch.setitem(sys.modules, "ultralytics", fake_module)


def test_model_loading_success(monkeypatch):
    _install_fake_ultralytics(monkeypatch, track_return=[])
    svc = DetectionService()
    svc.load_model()
    assert svc.is_ready is True
    assert svc.load_error is None


def test_model_loading_failure_sets_error_and_raises(monkeypatch):
    fake_module = types.ModuleType("ultralytics")

    def broken_yolo(_path):
        raise OSError("corrupt model file")

    fake_module.YOLO = broken_yolo
    monkeypatch.setitem(sys.modules, "ultralytics", fake_module)

    svc = DetectionService()
    with pytest.raises(Exception):
        svc.load_model()
    assert svc.is_ready is False
    assert "corrupt model file" in svc.load_error


def test_detect_and_track_output_structure(monkeypatch):
    fake_result = MagicMock()
    fake_result.names = {0: "person", 2: "car"}
    fake_boxes = MagicMock()
    fake_boxes.xyxy.cpu.return_value.numpy.return_value = np.array([[10.0, 10.0, 50.0, 90.0]])
    fake_boxes.conf.cpu.return_value.numpy.return_value = np.array([0.87])
    fake_boxes.cls.cpu.return_value.numpy.return_value.astype.return_value = np.array([0])
    fake_boxes.id.cpu.return_value.numpy.return_value.astype.return_value = np.array([42])
    fake_result.boxes = fake_boxes

    _install_fake_ultralytics(monkeypatch, track_return=[fake_result])

    svc = DetectionService()
    svc.load_model()
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    tracks = svc.detect_and_track(frame)

    assert len(tracks) == 1
    t = tracks[0]
    assert t.track_id == 42
    assert t.class_name == "person"
    assert t.confidence == pytest.approx(0.87)
    assert t.bbox == (10.0, 10.0, 50.0, 90.0)
    assert t.center_x == 30.0
    assert t.center_y == 50.0
    d = t.to_dict()
    assert set(d.keys()) == {
        "track_id", "class_id", "class_name", "confidence",
        "bbox", "center_x", "center_y", "timestamp",
    }


def test_detect_and_track_without_loaded_model_raises():
    svc = DetectionService()
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    with pytest.raises(RuntimeError):
        svc.detect_and_track(frame)


def test_detect_and_track_handles_no_track_ids_gracefully(monkeypatch):
    fake_result = MagicMock()
    fake_boxes = MagicMock()
    fake_boxes.id = None  # no tracks assigned yet this frame
    fake_result.boxes = fake_boxes
    _install_fake_ultralytics(monkeypatch, track_return=[fake_result])

    svc = DetectionService()
    svc.load_model()
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    tracks = svc.detect_and_track(frame)
    assert tracks == []
