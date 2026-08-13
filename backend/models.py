"""
models.py

SQLAlchemy ORM models for EagleWatch AI.

Field names deliberately mirror the concepts already used in the
existing React frontend (EagleWatch_AI_Demo.jsx):

    id, category, label, location, confidence, severity, status,
    x, y, camera_id, created_at (-> frontend's `time`)
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Float, DateTime, Integer
from database import Base


def generate_incident_id() -> str:
    """
    Generates ids in the same visual style the frontend already uses,
    e.g. INC-2291, INC-2305 ...
    """
    return f"INC-{uuid.uuid4().int % 9000 + 1000}"


class Incident(Base):
    __tablename__ = "incidents"

    # Primary key kept as a string ("INC-xxxx") to match the frontend's
    # existing incident id format instead of a raw integer.
    id = Column(String, primary_key=True, default=generate_incident_id)

    # "accident" | "safety"  (matches SCENARIOS / SEED_INCIDENTS in the frontend)
    category = Column(String, nullable=False, index=True)

    # Human readable incident name, e.g. "Vehicle Collision"
    label = Column(String, nullable=False)

    # Short one-line description, e.g. "Two-vehicle junction impact"
    # (matches the `sub` field used in the frontend's SCENARIOS list)
    sub = Column(String, nullable=True)

    location = Column(String, nullable=False, index=True)

    # Camera that produced the detection, e.g. "CAM-04"
    camera_id = Column(String, nullable=True)

    # AI confidence percentage (0-100)
    confidence = Column(Integer, nullable=False, default=0)

    # True underlying severity: "critical" | "high" | "medium"
    # NOTE: the frontend's demo data also (confusingly) reuses this field
    # with the value "resolved" purely for badge coloring. The backend
    # keeps this column as the *real* severity level at all times, and
    # the API layer (schemas.py) derives a frontend-friendly
    # `display_severity` that becomes "resolved" once status == "Resolved".
    severity = Column(String, nullable=False, index=True)

    # Detected -> Verified -> Alerted -> Responding -> Resolved
    status = Column(String, nullable=False, default="Detected", index=True)

    # Map coordinates on the frontend's 0-100 viewBox grid
    x = Column(Float, nullable=True)
    y = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
