"""
services/incident_service.py

Core business logic for EagleWatch AI incidents:
  - demo scenario definitions (mirrors frontend SCENARIOS)
  - seed data (mirrors frontend SEED_INCIDENTS)
  - status transition rules
  - stats / analytics aggregation

Kept as plain functions (no framework dependencies) so it's easy to
unit test and easy to later swap the demo scenario source for a real
AI detection pipeline.
"""

import random
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ai_config import config
from models import Incident, generate_incident_id
from schemas import STATUS_ORDER

# ---------------------------------------------------------------------
# Demo scenarios (identical data to the frontend's SCENARIOS array)
# ---------------------------------------------------------------------

SCENARIOS = {
    "collision": {
        "category": "accident",
        "label": "Vehicle Collision",
        "sub": "Two-vehicle junction impact",
        "location": "Anna Salai & Mount Rd Jn",
        "camera_id": "CAM-04",
        "confidence": 94,
        "severity": "critical",
    },
    "twowheeler": {
        "category": "accident",
        "label": "Two-Wheeler Accident",
        "sub": "Single-vehicle loss of control",
        "location": "ECR Coastal Road, KM 12",
        "camera_id": "CAM-11",
        "confidence": 88,
        "severity": "high",
    },
    "distress": {
        "category": "safety",
        "label": "Women Safety Incident",
        "sub": "Potential distress / isolated individual, erratic motion",
        "location": "T Nagar Bus Terminus",
        "camera_id": "CAM-07",
        "confidence": 91,
        "severity": "critical",
    },
    # "normal" (Normal Traffic) is intentionally NOT a demo scenario -
    # normal traffic must never create an incident, in either AI_MODE.
    # See frontend App.jsx runDetection() for the demo-mode no-op path
    # and services/event_analyzer.py for why real YOLO/ByteTrack
    # detections of ordinary vehicles/pedestrians don't fire an event.
}


# ---------------------------------------------------------------------
# Seed data (mirrors frontend SEED_INCIDENTS, statuses adjusted to be
# valid final/intermediate states in the backend's stricter lifecycle)
# ---------------------------------------------------------------------

def _mins_ago(n: int) -> datetime:
    return datetime.utcnow() - timedelta(minutes=n)


def _seed_rows():
    return [
        dict(id="INC-2291", category="accident", label="Vehicle Collision",
             location="Kathipara Flyover", severity="critical", confidence=92,
             status="Resolved", created_at=_mins_ago(240), x=62, y=58,
             camera_id="CAM-04", sub="Two-vehicle junction impact"),
        dict(id="INC-2294", category="safety", label="Potential Distress Signal",
             location="Guindy Metro Exit", severity="critical", confidence=89,
             status="Resolved", created_at=_mins_ago(190), x=47, y=40,
             camera_id="CAM-07", sub="Isolated individual, erratic motion"),
        dict(id="INC-2299", category="accident", label="Two-Wheeler Fall",
             location="OMR Sholinganallur", severity="medium", confidence=81,
             status="Alerted", created_at=_mins_ago(96), x=78, y=71,
             camera_id="CAM-11", sub="Single-vehicle loss of control"),
        dict(id="INC-2302", category="safety", label="Suspicious Pursuit Pattern",
             location="Velachery Underpass", severity="high", confidence=87,
             status="Verified", created_at=_mins_ago(41), x=55, y=66,
             camera_id="CAM-19", sub="Sustained follow behaviour detected"),
        dict(id="INC-2305", category="accident", label="Vehicle Collision",
             location="Anna Salai & Mount Rd Jn", severity="critical", confidence=95,
             status="Responding", created_at=_mins_ago(12), x=40, y=33,
             camera_id="CAM-04", sub="Two-vehicle junction impact"),
        dict(id="INC-2307", category="safety", label="Potential Distress Signal",
             location="T Nagar Bus Terminus", severity="critical", confidence=90,
             status="Alerted", created_at=_mins_ago(4), x=35, y=52,
             camera_id="CAM-07", sub="Isolated individual, erratic motion"),
    ]


def seed_if_empty(db: Session) -> None:
    """Inserts demo seed incidents only if the table is currently empty,
    so restarting the server never creates duplicates."""
    existing = db.query(Incident).count()
    if existing > 0:
        return

    for row in _seed_rows():
        db.add(Incident(**row))
    db.commit()


# ---------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------

def create_incident_from_scenario(db: Session, scenario_id: str) -> Incident:
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario_id}'. "
                          f"Valid options: {list(SCENARIOS.keys())}")

    s = SCENARIOS[scenario_id]

    # Small jitter on confidence, same spirit as the frontend demo runner
    jitter = random.randint(-2, 2)
    confidence = max(1, min(99, s["confidence"] + jitter))

    incident = Incident(
        id=generate_incident_id(),
        category=s["category"],
        label=s["label"],
        sub=s["sub"],
        location=s["location"],
        camera_id=s["camera_id"],
        confidence=confidence,
        severity=s["severity"],
        status="Detected",
        x=round(30 + random.random() * 45, 2),
        y=round(30 + random.random() * 45, 2),
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def create_incident_from_ai(
    db: Session,
    category: str,
    label: str,
    sub: str,
    camera_id: str,
    confidence: int,
    severity: str,
) -> Incident:
    """
    Creates an incident from a real, confirmed AI detection (YOLO +
    ByteTrack + event_analyzer). Location/x/y come from the configured
    camera metadata (ai_config) since a normal video feed carries no
    GPS information - see README "Location" section.
    """
    incident = Incident(
        id=generate_incident_id(),
        category=category,
        label=label,
        sub=sub,
        location=config.CAMERA_LOCATION,
        camera_id=camera_id,
        confidence=max(0, min(100, confidence)),
        severity=severity,
        status="Detected",
        x=config.CAMERA_X,
        y=config.CAMERA_Y,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


# ---------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------

class InvalidTransitionError(Exception):
    pass


def advance_status(db: Session, incident: Incident, target_status: str) -> Incident:
    """Moves an incident exactly one step forward in STATUS_ORDER.
    Raises InvalidTransitionError if the move is not legal."""

    current_index = STATUS_ORDER.index(incident.status)
    target_index = STATUS_ORDER.index(target_status)

    if target_index != current_index + 1:
        raise InvalidTransitionError(
            f"Cannot move incident {incident.id} from '{incident.status}' "
            f"to '{target_status}'. Expected next status: "
            f"'{STATUS_ORDER[current_index + 1] if current_index + 1 < len(STATUS_ORDER) else 'none'}'."
        )

    incident.status = target_status
    incident.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(incident)
    return incident


# ---------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------

def compute_stats(db: Session) -> dict:
    total = db.query(Incident).count()
    resolved = db.query(Incident).filter(Incident.status == "Resolved").count()
    active = total - resolved

    accidents = db.query(Incident).filter(Incident.category == "accident").count()
    safety = db.query(Incident).filter(Incident.category == "safety").count()

    critical = db.query(Incident).filter(Incident.severity == "critical").count()
    high = db.query(Incident).filter(Incident.severity == "high").count()
    medium = db.query(Incident).filter(Incident.severity == "medium").count()

    avg_response = _average_response_time_minutes(db)

    return {
        "active_incidents": active,
        "total_incidents": total,
        "accidents": accidents,
        "safety_events": safety,
        "critical_incidents": critical,
        "high_incidents": high,
        "medium_incidents": medium,
        "resolved_incidents": resolved,
        "avg_response_time_minutes": avg_response,
    }


def _average_response_time_minutes(db: Session) -> Optional[float]:
    """Average time (in minutes) between creation and resolution for
    incidents that have reached 'Resolved'. Returns None if no
    resolved incidents exist yet (nothing to average)."""
    resolved = db.query(Incident).filter(Incident.status == "Resolved").all()
    if not resolved:
        return None

    total_minutes = sum(
        (inc.updated_at - inc.created_at).total_seconds() / 60.0 for inc in resolved
    )
    return round(total_minutes / len(resolved), 1)


# ---------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------

def compute_analytics(db: Session) -> dict:
    by_type_rows = (
        db.query(Incident.label, func.count(Incident.id))
        .group_by(Incident.label)
        .all()
    )
    by_type = [{"name": label, "count": count} for label, count in by_type_rows]

    by_severity_rows = (
        db.query(Incident.severity, func.count(Incident.id))
        .group_by(Incident.severity)
        .all()
    )
    by_severity = [{"severity": sev, "count": count} for sev, count in by_severity_rows]

    location_rows = (
        db.query(Incident.location, func.count(Incident.id))
        .group_by(Incident.location)
        .order_by(func.count(Incident.id).desc())
        .limit(5)
        .all()
    )
    high_risk_locations = [{"location": loc, "count": count} for loc, count in location_rows]

    recent = (
        db.query(Incident)
        .order_by(Incident.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "by_type": by_type,
        "by_severity": by_severity,
        "high_risk_locations": high_risk_locations,
        "avg_response_time_minutes": _average_response_time_minutes(db),
        "recent_incidents": recent,
    }
