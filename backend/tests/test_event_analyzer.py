import time

from ai_config import config
from services.detection_service import TrackedObject
from services.event_analyzer import EventAnalyzer, _iou
from services.tracking_service import HistoryPoint


def make_track(track_id, class_name, bbox, confidence=0.9, ts=None):
    x1, y1, x2, y2 = bbox
    return TrackedObject(
        track_id=track_id,
        class_id=0,
        class_name=class_name,
        confidence=confidence,
        bbox=bbox,
        center_x=(x1 + x2) / 2,
        center_y=(y1 + y2) / 2,
        timestamp=ts or time.time(),
    )


def make_history_point(cx, cy, w=40, h=80, class_name="person", ts=None):
    return HistoryPoint(
        timestamp=ts or time.time(),
        center_x=cx, center_y=cy, width=w, height=h,
        class_name=class_name, confidence=0.9,
    )


def test_iou_no_overlap_is_zero():
    assert _iou((0, 0, 10, 10), (100, 100, 110, 110)) == 0.0


def test_iou_full_overlap_is_one():
    assert _iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0


def test_vehicle_collision_candidate_on_high_overlap():
    analyzer = EventAnalyzer()
    car_a = make_track(1, "car", (100, 100, 200, 200))
    car_b = make_track(2, "car", (120, 100, 220, 200))  # heavy overlap
    candidates = analyzer._detect_vehicle_collision([car_a, car_b], {})
    assert len(candidates) == 1
    assert candidates[0].event_type == "collision"
    assert candidates[0].category == "accident"


def test_no_collision_when_vehicles_far_apart():
    analyzer = EventAnalyzer()
    car_a = make_track(1, "car", (0, 0, 50, 50))
    car_b = make_track(2, "car", (500, 500, 550, 550))
    candidates = analyzer._detect_vehicle_collision([car_a, car_b], {})
    assert candidates == []


def test_two_wheeler_overlap_flags_incident():
    analyzer = EventAnalyzer()
    bike = make_track(3, "motorcycle", (100, 100, 140, 180))
    car = make_track(4, "car", (110, 100, 200, 200))
    candidates = analyzer._detect_two_wheeler_incident([bike, car], {})
    assert len(candidates) == 1
    assert candidates[0].event_type == "two_wheeler"


def test_person_fall_requires_prior_standing_posture():
    analyzer = EventAnalyzer()
    camera_id = "CAM-TEST"
    now = time.time()

    # History: standing (tall/narrow) then suddenly lying (wide/short)
    history = {
        7: [
            make_history_point(100, 100, w=30, h=90, ts=now - 2.0),
            make_history_point(102, 101, w=30, h=88, ts=now - 1.5),
            make_history_point(105, 150, w=90, h=30, ts=now - 0.1),
        ]
    }
    person = make_track(7, "person", (60, 135, 150, 165), ts=now)

    # First call starts the fall timer, shouldn't confirm instantly.
    candidates = analyzer._detect_person_fall(camera_id, [person], history)
    assert candidates == []

    # Simulate enough elapsed time for FALL_CONFIRM_SECONDS to pass.
    later_person = make_track(7, "person", (60, 135, 150, 165), ts=now + 1.5)
    candidates = analyzer._detect_person_fall(camera_id, [later_person], history)
    assert len(candidates) == 1
    assert candidates[0].event_type == "fall"
    assert candidates[0].category == "safety"


def test_pursuit_requires_closeness_and_shared_direction():
    analyzer = EventAnalyzer()
    camera_id = "CAM-TEST"
    now = time.time()

    history = {
        1: [make_history_point(100, 100, ts=now - 0.2), make_history_point(110, 100, ts=now)],
        2: [make_history_point(140, 100, ts=now - 0.2), make_history_point(150, 100, ts=now)],
    }
    person_a = make_track(1, "person", (95, 80, 125, 160), ts=now)
    person_b = make_track(2, "person", (135, 80, 165, 160), ts=now)

    candidates = analyzer._detect_pursuit(camera_id, [person_a, person_b], history)
    # Not confirmed yet - condition only just started.
    assert candidates == []

    later_a = make_track(1, "person", (95, 80, 125, 160), ts=now + 4)
    later_b = make_track(2, "person", (135, 80, 165, 160), ts=now + 4)
    history[1].append(make_history_point(112, 100, ts=now + 4))
    history[2].append(make_history_point(152, 100, ts=now + 4))
    candidates = analyzer._detect_pursuit(camera_id, [later_a, later_b], history)
    assert len(candidates) == 1
    assert candidates[0].event_type == "pursuit"


def test_analyze_requires_temporal_confirmation_across_frames():
    analyzer = EventAnalyzer()
    camera_id = "CAM-TEST"
    car_a = make_track(1, "car", (100, 100, 200, 200))
    car_b = make_track(2, "car", (120, 100, 220, 200))

    confirmed = None
    for _ in range(config.EVENT_CONFIRM_FRAMES - 1):
        confirmed = analyzer.analyze(camera_id, [car_a, car_b], {})
        assert confirmed is None  # not yet confirmed

    confirmed = analyzer.analyze(camera_id, [car_a, car_b], {})
    assert confirmed is not None
    assert confirmed.event_type == "collision"


def test_analyze_returns_none_with_no_relevant_objects():
    analyzer = EventAnalyzer()
    person = make_track(9, "person", (0, 0, 30, 90))
    assert analyzer.analyze("CAM-TEST", [person], {}) is None
