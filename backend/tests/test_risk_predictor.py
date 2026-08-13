import time

from services.detection_service import TrackedObject
from services.risk_predictor import PreAccidentPredictor
from services.tracking_service import HistoryPoint


def _track(tid, cname, x, y, w=40, h=40, conf=0.9, ts=None):
    return TrackedObject(
        track_id=tid, class_id=0, class_name=cname, confidence=conf,
        bbox=(x - w / 2, y - h / 2, x + w / 2, y + h / 2),
        center_x=x, center_y=y, timestamp=ts or time.time(),
    )


def _hist(xs, ys, ts_list, w=40, h=40, cname="car"):
    return [
        HistoryPoint(timestamp=t, center_x=x, center_y=y, width=w, height=h, class_name=cname, confidence=0.9)
        for t, x, y in zip(ts_list, xs, ys)
    ]


def test_head_on_convergence_escalates_to_critical_after_debounce():
    p = PreAccidentPredictor()
    cam = "CAM-1"
    now = time.time()
    ts = [now - 0.4, now - 0.3, now - 0.2, now - 0.1, now]
    history = {
        1: _hist([100, 120, 140, 160, 180], [200] * 5, ts),
        2: _hist([500, 480, 460, 440, 420], [200] * 5, ts),
    }
    tA = _track(1, "car", 180, 200, ts=now)
    tB = _track(2, "car", 420, 200, ts=now)

    levels = [p.predict(cam, [tA, tB], history).risk_level for _ in range(6)]

    # Not reported until the condition has held for RISK_CONFIRM_FRAMES
    assert levels[0] == "NORMAL"
    # Eventually escalates and sustains at a real risk level
    assert levels[-1] in ("HIGH_RISK", "CRITICAL_RISK")


def test_head_on_convergence_reports_positive_probability_and_ttc():
    p = PreAccidentPredictor()
    cam = "CAM-1b"
    now = time.time()
    ts = [now - 0.4, now - 0.3, now - 0.2, now - 0.1, now]
    history = {
        1: _hist([100, 120, 140, 160, 180], [200] * 5, ts),
        2: _hist([500, 480, 460, 440, 420], [200] * 5, ts),
    }
    tA = _track(1, "car", 180, 200, ts=now)
    tB = _track(2, "car", 420, 200, ts=now)

    assessment = None
    for _ in range(6):
        assessment = p.predict(cam, [tA, tB], history)

    assert assessment.risk_type == "vehicle_collision"
    assert 0.0 < assessment.collision_probability <= 1.0
    assert assessment.time_to_collision is not None
    assert assessment.time_to_collision > 0
    assert set(assessment.involved_track_ids) == {1, 2}


def test_parallel_same_speed_traffic_never_flagged():
    """Two cars driving side by side at the same speed must never be
    reported as a collision risk - this is the spec's explicit
    false-positive example."""
    p = PreAccidentPredictor()
    cam = "CAM-2"
    now = time.time()
    ts = [now - 0.4, now - 0.3, now - 0.2, now - 0.1, now]
    history = {
        1: _hist([100, 120, 140, 160, 180], [180] * 5, ts),
        2: _hist([100, 120, 140, 160, 180], [220] * 5, ts),
    }
    tA = _track(1, "car", 180, 180, ts=now)
    tB = _track(2, "car", 180, 220, ts=now)

    for _ in range(10):
        assessment = p.predict(cam, [tA, tB], history)
        assert assessment.risk_level == "NORMAL"


def test_car_that_already_passed_is_not_flagged():
    """A faster car that has already overtaken and is pulling away must
    not be flagged - the closest-approach time is in the past (t* < 0)."""
    p = PreAccidentPredictor()
    cam = "CAM-3"
    now = time.time()
    ts = [now - 0.4, now - 0.3, now - 0.2, now - 0.1, now]
    history = {
        1: _hist([100, 140, 180, 220, 260], [200] * 5, ts),  # fast car, now ahead
        2: _hist([150, 160, 170, 180, 190], [200] * 5, ts),  # slow car, now behind
    }
    tA = _track(1, "car", 260, 200, ts=now)
    tB = _track(2, "car", 190, 200, ts=now)

    for _ in range(10):
        assessment = p.predict(cam, [tA, tB], history)
        assert assessment.risk_level == "NORMAL"


def test_tailgating_approach_is_flagged_as_risk():
    """A car rapidly closing the gap on the car ahead of it in the same
    lane is a genuine, physically-justified risk."""
    p = PreAccidentPredictor()
    cam = "CAM-4"
    now = time.time()
    ts = [now - 0.4, now - 0.3, now - 0.2, now - 0.1, now]
    history = {
        1: _hist([60, 100, 140, 180, 220], [200] * 5, ts),   # fast car behind, catching up
        2: _hist([200, 210, 220, 230, 240], [200] * 5, ts),  # slow car ahead
    }
    tA = _track(1, "car", 220, 200, ts=now)
    tB = _track(2, "car", 240, 200, ts=now)

    levels = [p.predict(cam, [tA, tB], history).risk_level for _ in range(8)]
    assert levels[-1] in ("HIGH_RISK", "CRITICAL_RISK")


def test_two_wheeler_pair_is_classified_as_two_wheeler_collision():
    p = PreAccidentPredictor()
    cam = "CAM-5"
    now = time.time()
    ts = [now - 0.4, now - 0.3, now - 0.2, now - 0.1, now]
    history = {
        1: _hist([100, 120, 140, 160, 180], [200] * 5, ts, cname="motorcycle"),
        2: _hist([500, 480, 460, 440, 420], [200] * 5, ts, cname="car"),
    }
    tA = _track(1, "motorcycle", 180, 200, ts=now)
    tB = _track(2, "car", 420, 200, ts=now)

    assessment = None
    for _ in range(6):
        assessment = p.predict(cam, [tA, tB], history)
    assert assessment.risk_type == "two_wheeler_collision"


def test_persistent_close_following_flags_safety_risk():
    p = PreAccidentPredictor()
    cam = "CAM-SAFETY"
    now = time.time()
    ts = [now - 0.4, now - 0.3, now - 0.2, now - 0.1, now]
    history = {
        1: _hist([100, 110, 120, 130, 140], [200, 202, 204, 206, 208], ts, cname="person"),
        2: _hist([150, 158, 166, 174, 182], [205, 206, 207, 208, 209], ts, cname="person"),
    }
    tA = _track(1, "person", 140, 208, ts=now)
    tB = _track(2, "person", 182, 209, ts=now)

    levels = [p.predict(cam, [tA, tB], history).risk_level for _ in range(8)]
    assert levels[-1] in ("MEDIUM_RISK", "HIGH_RISK")

    final = p.predict(cam, [tA, tB], history)
    assert final.risk_type == "safety"
    assert "heuristic" in final.reason.lower() or "proxy" in final.reason.lower()


def test_solitary_person_never_flagged():
    p = PreAccidentPredictor()
    cam = "CAM-SOLO"
    now = time.time()
    ts = [now - 0.4, now - 0.2, now]
    history = {1: _hist([100, 120, 140], [200, 200, 200], ts, cname="person")}
    tA = _track(1, "person", 140, 200, ts=now)

    for _ in range(5):
        assessment = p.predict(cam, [tA], history)
        assert assessment.risk_level == "NORMAL"


def test_reset_clears_debounce_state_for_a_camera():
    p = PreAccidentPredictor()
    cam = "CAM-RESET"
    now = time.time()
    ts = [now - 0.4, now - 0.3, now - 0.2, now - 0.1, now]
    history = {
        1: _hist([100, 120, 140, 160, 180], [200] * 5, ts),
        2: _hist([500, 480, 460, 440, 420], [200] * 5, ts),
    }
    tA = _track(1, "car", 180, 200, ts=now)
    tB = _track(2, "car", 420, 200, ts=now)

    for _ in range(6):
        p.predict(cam, [tA, tB], history)
    assert p._confirm_counts.get(cam)  # some persistence built up

    p.reset(cam)
    assert cam not in p._confirm_counts
    # Immediately after reset, a single frame is never enough to report risk
    assert p.predict(cam, [tA, tB], history).risk_level == "NORMAL"
