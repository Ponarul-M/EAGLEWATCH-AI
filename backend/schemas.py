"""
schemas.py

Pydantic models used for request validation and JSON responses.
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict

# ---------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------

# Full lifecycle. The existing frontend only actively drives the first
# four stages (Detected -> Verified -> Alerted -> Responding), but the
# backend also supports a final "Resolved" stage.
STATUS_ORDER = ["Detected", "Verified", "Alerted", "Responding", "Resolved"]

VALID_SEVERITIES = {"critical", "high", "medium"}
VALID_CATEGORIES = {"accident", "safety"}


# ---------------------------------------------------------------------
# Incident schemas
# ---------------------------------------------------------------------

class IncidentBase(BaseModel):
    category: str
    label: str
    sub: Optional[str] = None
    location: str
    camera_id: Optional[str] = None
    confidence: int
    severity: str
    status: str
    x: Optional[float] = None
    y: Optional[float] = None


class IncidentOut(BaseModel):
    """Response shape returned to the frontend for a single incident."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    category: str
    label: str
    sub: Optional[str] = None
    location: str
    camera_id: Optional[str] = None
    confidence: int

    # Real severity level, always "critical" | "high" | "medium"
    severity: str

    # Frontend-facing severity used for badge coloring. Mirrors the
    # frontend's own demo data convention where a resolved incident's
    # badge shows "resolved" instead of its original severity.
    display_severity: str

    status: str
    x: Optional[float] = None
    y: Optional[float] = None

    created_at: datetime
    updated_at: datetime

    # Alias so frontend code that expects `time` (a JS Date) keeps working
    # without modification - see routes/incidents.py for how this is filled.
    time: datetime

    @staticmethod
    def from_model(inc) -> "IncidentOut":
        display_severity = "resolved" if inc.status == "Resolved" else inc.severity
        return IncidentOut(
            id=inc.id,
            category=inc.category,
            label=inc.label,
            sub=inc.sub,
            location=inc.location,
            camera_id=inc.camera_id,
            confidence=inc.confidence,
            severity=inc.severity,
            display_severity=display_severity,
            status=inc.status,
            x=inc.x,
            y=inc.y,
            created_at=inc.created_at,
            updated_at=inc.updated_at,
            time=inc.created_at,
        )


class IncidentListOut(BaseModel):
    incidents: List[IncidentOut]
    count: int


# ---------------------------------------------------------------------
# Demo detection schemas
# ---------------------------------------------------------------------

class DemoDetectionRequest(BaseModel):
    # Matches the scenario ids already defined in the frontend's
    # SCENARIOS array: collision | twowheeler | distress
    # (the "normal" scenario is intentionally NOT in this list - normal
    # traffic never creates a demo incident, see App.jsx runDetection())
    scenario: str = Field(..., examples=["collision"])


# ---------------------------------------------------------------------
# Stats / analytics schemas
# ---------------------------------------------------------------------

class StatsOut(BaseModel):
    active_incidents: int
    total_incidents: int
    accidents: int
    safety_events: int
    critical_incidents: int
    high_incidents: int
    medium_incidents: int
    resolved_incidents: int
    avg_response_time_minutes: Optional[float] = None


class MapIncidentOut(BaseModel):
    id: str
    label: str
    location: str
    category: str
    severity: str
    display_severity: str
    status: str
    confidence: int
    x: Optional[float] = None
    y: Optional[float] = None
    time: datetime


class MapDataOut(BaseModel):
    incidents: List[MapIncidentOut]


class TypeCount(BaseModel):
    name: str
    count: int


class SeverityCount(BaseModel):
    severity: str
    count: int


class LocationCount(BaseModel):
    location: str
    count: int


class AnalyticsOut(BaseModel):
    by_type: List[TypeCount]
    by_severity: List[SeverityCount]
    high_risk_locations: List[LocationCount]
    avg_response_time_minutes: Optional[float] = None
    recent_incidents: List[IncidentOut]
