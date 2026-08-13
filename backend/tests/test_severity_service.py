from services.severity_service import compute_confidence, compute_severity


def test_collision_high_overlap_is_critical():
    sev = compute_severity("collision", {"objects_involved": 2, "overlap_iou": 0.5, "sudden_deceleration": False})
    assert sev == "critical"


def test_collision_low_overlap_no_decel_is_high():
    sev = compute_severity("collision", {"objects_involved": 2, "overlap_iou": 0.15, "sudden_deceleration": False})
    assert sev == "high"


def test_two_wheeler_stop_and_overlap_is_critical():
    sev = compute_severity("two_wheeler", {"sudden_stop": True, "overlap_iou": 0.2})
    assert sev == "critical"


def test_two_wheeler_stop_only_is_high():
    sev = compute_severity("two_wheeler", {"sudden_stop": True, "overlap_iou": 0.0})
    assert sev == "high"


def test_fall_long_duration_is_critical():
    assert compute_severity("fall", {"elapsed_seconds": 5.0}) == "critical"


def test_fall_short_duration_is_high():
    assert compute_severity("fall", {"elapsed_seconds": 1.5}) == "high"


def test_pursuit_is_medium():
    assert compute_severity("pursuit", {}) == "medium"


def test_confidence_never_random_and_bounded():
    c1 = compute_confidence(0.9, confirm_frames=5, required_frames=5)
    c2 = compute_confidence(0.9, confirm_frames=5, required_frames=5)
    assert c1 == c2  # deterministic, not random
    assert 0 <= c1 <= 100


def test_confidence_clamped_at_100():
    c = compute_confidence(1.0, confirm_frames=50, required_frames=5)
    assert c <= 100


def test_confidence_reflects_detection_confidence():
    low = compute_confidence(0.4, confirm_frames=5, required_frames=5)
    high = compute_confidence(0.9, confirm_frames=5, required_frames=5)
    assert high > low
