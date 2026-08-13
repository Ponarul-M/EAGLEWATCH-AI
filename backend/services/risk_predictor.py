"""
services/risk_predictor.py

STAGE 1 of the two-stage pipeline: PRE-ACCIDENT RISK PREDICTION.

This module never decides that an accident happened - that's still
services/event_analyzer.py's job (Stage 2: confirmation, unchanged).
This module only asks: "given where these tracked objects have been
and how fast they're moving, are they on a course that will bring
them dangerously close soon?"

Everything here is plain kinematics on top of the existing ByteTrack
history (services/tracking_service.py) - no new model, no randomness,
no knowledge of the future frame number or the video filename.

--------------------------------------------------------------------
THE PHYSICS (collision risk between two vehicles/two-wheelers)
--------------------------------------------------------------------
For two tracked objects A and B, using their estimated velocity
vectors (from recent position history):

    relative position:  d  = pos_B - pos_A
    relative velocity:  rv = vel_B - vel_A

Treating both as moving in straight lines, the time at which they are
closest to each other (their "closest point of approach") is:

    t* = -(d . rv) / |rv|^2

  - t* < 0  -> closest approach was in the past; they're separating.
              (This is exactly what keeps two cars overtaking cleanly,
              or moving apart, from ever being flagged: t* comes out
              negative and the pair is skipped outright.)
  - t* > 0  -> they are still approaching. Projecting both positions
              forward by t* gives the predicted minimum distance
              between them. A short t* + a small predicted minimum
              distance is a genuine, physically-grounded collision
              warning - not a guess.

Two cars driving side by side at the same speed have rv ~= 0, so
|rv|^2 ~= 0 and the pair is skipped (division guarded) - this is why
that case can never trigger a false "collision risk" here.

--------------------------------------------------------------------
THE SAFETY-RISK SIGNAL (women's safety scenario)
--------------------------------------------------------------------
YOLO/ByteTrack cannot know anyone's intent. What CAN be measured from
tracking data alone: two people staying unusually close together while
moving in a similar direction, and how long that's been going on. That
proximity + shared-direction + persistence combination is used as a
transparent, honestly-limited proxy - never dressed up as "the system
detected a threat". See the `reason` string and README limitations.

--------------------------------------------------------------------
DEBOUNCING
--------------------------------------------------------------------
A pair's raw, instantaneous risk is only reported once it has held for
RISK_CONFIRM_FRAMES consecutive frames (config), and decays by one
frame of "credit" per frame it's absent - the same temporal-smoothing
idea event_analyzer.py already uses for accident confirmation, just on
a shorter fuse so the warning shows up earlier than the confirmation.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ai_config import config
from services.detection_service import PERSON_CLASS, TWO_WHEELER_CLASSES, TrackedObject, VEHICLE_CLASSES
from services.tracking_service import HistoryPoint

logger = logging.getLogger("eaglewatch.ai.risk")

# Person-pair proximity used for the safety-risk signal (mirrors
# event_analyzer's pursuit-confirmation distance so the "warning" and
# the later "confirmation" agree on what counts as "close").
SAFETY_PROXIMITY_PX = 260.0
SAFETY_DIRECTION_COS_SIM_MIN = 0.3

RISK_RANK = {"NORMAL": 0, "LOW_RISK": 1, "MEDIUM_RISK": 2, "HIGH_RISK": 3, "CRITICAL_RISK": 4, "ACCIDENT_CONFIRMED": 5}


@dataclass
class RiskCandidate:
    key: str                       # debounce key, e.g. "collision:3-7"
    risk_type: str                 # "vehicle_collision" | "two_wheeler_collision" | "safety"
    collision_probability: float   # 0.0 - 1.0, always computed, never random
    time_to_collision: Optional[float]
    reason: str
    involved_track_ids: List[int]
    instantaneous_level: str       # risk level this single frame would justify, pre-debounce


@dataclass
class RiskAssessment:
    risk_level: str = "NORMAL"
    risk_type: Optional[str] = None
    collision_probability: float = 0.0
    time_to_collision: Optional[float] = None
    reason: str = ""
    involved_track_ids: List[int] = field(default_factory=list)
    # Every candidate pair considered this frame (debounced or not) -
    # used by the video overlay to draw connecting lines/TTC text on
    # anything currently trending risky, not just the single top result.
    raw_candidates: List[RiskCandidate] = field(default_factory=list)


def _estimate_velocity(history: List[HistoryPoint], window: int = 5):
    """Average velocity vector (px/s) over the last `window` points."""
    pts = history[-window:]
    if len(pts) < 2:
        return None
    dt_total = pts[-1].timestamp - pts[0].timestamp
    if dt_total <= 1e-3:
        return None
    vx = (pts[-1].center_x - pts[0].center_x) / dt_total
    vy = (pts[-1].center_y - pts[0].center_y) / dt_total
    return vx, vy


def _closest_approach(pos_a, vel_a, pos_b, vel_b):
    """
    Returns (t_star, predicted_min_distance) for two linearly-moving
    points, or None if they're not meaningfully converging (moving
    apart, parallel, or the closest approach already happened).
    """
    dx = pos_b[0] - pos_a[0]
    dy = pos_b[1] - pos_a[1]
    rvx = vel_b[0] - vel_a[0]
    rvy = vel_b[1] - vel_a[1]

    rel_speed_sq = rvx * rvx + rvy * rvy
    rel_speed = math.sqrt(rel_speed_sq)
    if rel_speed < config.MIN_CLOSING_SPEED_PX_S:
        return None  # not enough relative motion to say anything meaningful

    t_star = -(dx * rvx + dy * rvy) / rel_speed_sq
    if t_star < 0:
        return None  # closest approach already passed - separating, not converging

    future_dx = dx + rvx * t_star
    future_dy = dy + rvy * t_star
    min_dist = math.hypot(future_dx, future_dy)
    return t_star, min_dist


def _probability_from_ttc(t_star: float, min_dist: float) -> float:
    proximity_score = max(0.0, min(1.0, 1 - min_dist / (config.COLLISION_DISTANCE_PX * 2.5)))
    ttc_score = max(0.0, min(1.0, 1 - t_star / config.TTC_HORIZON_SECONDS))
    return max(0.0, min(1.0, 0.5 * proximity_score + 0.5 * ttc_score))


def _level_from_ttc_probability(probability: float, t_star: float) -> str:
    if probability >= 0.75 and t_star <= 1.5:
        return "CRITICAL_RISK"
    if probability >= 0.55 and t_star <= 3.0:
        return "HIGH_RISK"
    if probability >= 0.30:
        return "MEDIUM_RISK"
    return "LOW_RISK"


class PreAccidentPredictor:
    """
    Stateful per-camera predictor. Call `predict()` once per processed
    frame with the same `tracks`/`history` the event_analyzer sees.
    """

    def __init__(self):
        # camera_id -> { candidate_key: consecutive_frame_count }
        self._confirm_counts: Dict[str, Dict[str, int]] = {}
        self._last_logged_level: Dict[str, str] = {}

    def reset(self, camera_id: str) -> None:
        self._confirm_counts.pop(camera_id, None)
        self._last_logged_level.pop(camera_id, None)

    def predict(
        self,
        camera_id: str,
        tracks: List[TrackedObject],
        history: Dict[int, List[HistoryPoint]],
    ) -> RiskAssessment:
        candidates: List[RiskCandidate] = []
        candidates += self._collision_candidates(tracks, history)
        candidates += self._safety_candidates(camera_id, tracks, history)

        counts = self._confirm_counts.setdefault(camera_id, {})
        seen_keys = set()
        sustained: List[RiskCandidate] = []

        for cand in candidates:
            seen_keys.add(cand.key)
            counts[cand.key] = counts.get(cand.key, 0) + 1
            if counts[cand.key] >= config.RISK_CONFIRM_FRAMES:
                sustained.append(cand)

        for key in list(counts.keys()):
            if key not in seen_keys:
                counts[key] = max(0, counts[key] - 1)
                if counts[key] == 0:
                    del counts[key]

        assessment = RiskAssessment(raw_candidates=candidates)
        if sustained:
            top = max(sustained, key=lambda c: c.collision_probability)
            assessment.risk_level = top.instantaneous_level
            assessment.risk_type = top.risk_type
            assessment.collision_probability = round(top.collision_probability, 3)
            assessment.time_to_collision = round(top.time_to_collision, 2) if top.time_to_collision is not None else None
            assessment.reason = top.reason
            assessment.involved_track_ids = top.involved_track_ids

        self._maybe_log(camera_id, assessment)
        return assessment

    # -------------------------------------------------------------
    # Vehicle / two-wheeler collision risk
    # -------------------------------------------------------------

    def _collision_candidates(
        self, tracks: List[TrackedObject], history: Dict[int, List[HistoryPoint]]
    ) -> List[RiskCandidate]:
        movers = [t for t in tracks if t.class_name in VEHICLE_CLASSES | TWO_WHEELER_CLASSES]
        out: List[RiskCandidate] = []

        for i in range(len(movers)):
            for j in range(i + 1, len(movers)):
                a, b = movers[i], movers[j]
                vel_a = _estimate_velocity(history.get(a.track_id, []))
                vel_b = _estimate_velocity(history.get(b.track_id, []))
                if vel_a is None or vel_b is None:
                    continue

                approach = _closest_approach((a.center_x, a.center_y), vel_a, (b.center_x, b.center_y), vel_b)
                if approach is None:
                    continue
                t_star, min_dist = approach
                if t_star > config.TTC_HORIZON_SECONDS or min_dist > config.COLLISION_DISTANCE_PX * 2.5:
                    continue  # too far in the future / never gets close enough to matter

                probability = _probability_from_ttc(t_star, min_dist)
                level = _level_from_ttc_probability(probability, t_star)
                if level == "LOW_RISK":
                    continue  # not worth surfacing as a candidate at all

                risk_type = "two_wheeler_collision" if (
                    a.class_name in TWO_WHEELER_CLASSES or b.class_name in TWO_WHEELER_CLASSES
                ) else "vehicle_collision"

                reason = (
                    f"Converging trajectories: projected {min_dist:.0f}px apart "
                    f"in {t_star:.1f}s (closing)"
                )

                out.append(RiskCandidate(
                    key=f"collision:{min(a.track_id, b.track_id)}-{max(a.track_id, b.track_id)}",
                    risk_type=risk_type,
                    collision_probability=probability,
                    time_to_collision=t_star,
                    reason=reason,
                    involved_track_ids=[a.track_id, b.track_id],
                    instantaneous_level=level,
                ))
        return out

    # -------------------------------------------------------------
    # Safety risk (women's safety scenario): proximity + shared
    # direction + persistence. See module docstring for the honesty
    # caveat - this is a heuristic proxy, not intent recognition.
    # -------------------------------------------------------------

    def _safety_candidates(
        self, camera_id: str, tracks: List[TrackedObject], history: Dict[int, List[HistoryPoint]]
    ) -> List[RiskCandidate]:
        people = [t for t in tracks if t.class_name == PERSON_CLASS]
        out: List[RiskCandidate] = []
        camera_counts = self._confirm_counts.get(camera_id, {})

        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                a, b = people[i], people[j]
                dist = math.hypot(a.center_x - b.center_x, a.center_y - b.center_y)
                if dist > SAFETY_PROXIMITY_PX:
                    continue

                dir_sim = self._direction_similarity(history.get(a.track_id, []), history.get(b.track_id, []))
                if dir_sim is None or dir_sim < SAFETY_DIRECTION_COS_SIM_MIN:
                    continue

                key = f"safety:{min(a.track_id, b.track_id)}-{max(a.track_id, b.track_id)}"
                persistence = camera_counts.get(key, 0)
                persistence_score = max(0.0, min(1.0, persistence / config.RISK_CONFIRM_FRAMES))
                proximity_score = max(0.0, min(1.0, 1 - dist / SAFETY_PROXIMITY_PX))
                direction_score = max(0.0, min(1.0, (dir_sim - SAFETY_DIRECTION_COS_SIM_MIN) / (1 - SAFETY_DIRECTION_COS_SIM_MIN)))

                probability = max(0.0, min(1.0, 0.45 * proximity_score + 0.30 * direction_score + 0.25 * persistence_score))
                if probability < 0.30:
                    continue

                level = "HIGH_RISK" if probability >= 0.6 else "MEDIUM_RISK"
                reason = (
                    "Persistent close-following pattern (proximity + shared direction). "
                    "Heuristic proxy only - not verified intent."
                )

                out.append(RiskCandidate(
                    key=key,
                    risk_type="safety",
                    collision_probability=probability,
                    time_to_collision=None,
                    reason=reason,
                    involved_track_ids=[a.track_id, b.track_id],
                    instantaneous_level=level,
                ))
        return out

    @staticmethod
    def _direction_similarity(hist_a: List[HistoryPoint], hist_b: List[HistoryPoint]) -> Optional[float]:
        if len(hist_a) < 2 or len(hist_b) < 2:
            return None
        vax = hist_a[-1].center_x - hist_a[-2].center_x
        vay = hist_a[-1].center_y - hist_a[-2].center_y
        vbx = hist_b[-1].center_x - hist_b[-2].center_x
        vby = hist_b[-1].center_y - hist_b[-2].center_y
        mag_a = math.hypot(vax, vay)
        mag_b = math.hypot(vbx, vby)
        if mag_a < 1e-3 or mag_b < 1e-3:
            return None
        return (vax * vbx + vay * vby) / (mag_a * mag_b)

    # -------------------------------------------------------------
    # Debug logging (spec section "TESTING"): only logs on level
    # changes, never per-frame, to avoid spamming the console.
    # -------------------------------------------------------------

    def _maybe_log(self, camera_id: str, assessment: RiskAssessment) -> None:
        last = self._last_logged_level.get(camera_id, "NORMAL")
        if assessment.risk_level == last:
            return
        self._last_logged_level[camera_id] = assessment.risk_level

        if RISK_RANK.get(assessment.risk_level, 0) > RISK_RANK.get(last, 0):
            if assessment.time_to_collision is not None:
                logger.info(
                    f"[AI] Risk -> {assessment.risk_level} ({assessment.risk_type}) "
                    f"prob={assessment.collision_probability:.2f} "
                    f"TTC={assessment.time_to_collision:.1f}s "
                    f"tracks={assessment.involved_track_ids} - {assessment.reason}"
                )
            else:
                logger.info(
                    f"[AI] Risk -> {assessment.risk_level} ({assessment.risk_type}) "
                    f"prob={assessment.collision_probability:.2f} "
                    f"tracks={assessment.involved_track_ids} - {assessment.reason}"
                )
        else:
            logger.info(f"[AI] Risk -> {assessment.risk_level}")


# Module-level singleton shared by the AI worker.
risk_predictor = PreAccidentPredictor()
