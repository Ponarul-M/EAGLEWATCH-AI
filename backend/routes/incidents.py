"""
routes/incidents.py

Incident listing, detail, lifecycle transitions, stats, and map data.
"""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Incident
import schemas
from services import incident_service
from services.incident_service import InvalidTransitionError

router = APIRouter(prefix="/api/incidents", tags=["Incidents"])


# NOTE: /stats and /map must be declared before /{incident_id} so
# FastAPI doesn't try to match them as an incident id.

@router.get(
    "/stats",
    response_model=schemas.StatsOut,
    summary="Dashboard statistics",
    description="Aggregate counts used by the EagleWatch dashboard cards "
                "(active/total incidents, category and severity breakdowns, "
                "average response time).",
)
def get_stats(db: Session = Depends(get_db)):
    return incident_service.compute_stats(db)


@router.get(
    "/map",
    response_model=schemas.MapDataOut,
    summary="Incident map data",
    description="Returns incidents with location + severity so the frontend "
                "can render markers on the Incident Map view.",
)
def get_map_data(db: Session = Depends(get_db)):
    incidents = db.query(Incident).order_by(Incident.created_at.desc()).all()
    out = [
        schemas.MapIncidentOut(
            id=i.id,
            label=i.label,
            location=i.location,
            category=i.category,
            severity=i.severity,
            display_severity="resolved" if i.status == "Resolved" else i.severity,
            status=i.status,
            confidence=i.confidence,
            x=i.x,
            y=i.y,
            time=i.created_at,
        )
        for i in incidents
    ]
    return schemas.MapDataOut(incidents=out)


@router.get(
    "",
    response_model=schemas.IncidentListOut,
    summary="List incidents",
    description="Returns all incidents, optionally filtered by `severity` "
                "and/or `status`. Example: /api/incidents?severity=critical",
)
def list_incidents(
    severity: Optional[str] = Query(None, description="critical | high | medium"),
    status_: Optional[str] = Query(None, alias="status", description="Detected | Verified | Alerted | Responding | Resolved"),
    db: Session = Depends(get_db),
):
    query = db.query(Incident)

    if severity:
        query = query.filter(Incident.severity == severity)
    if status_:
        query = query.filter(Incident.status == status_)

    incidents = query.order_by(Incident.created_at.desc()).all()
    out: List[schemas.IncidentOut] = [schemas.IncidentOut.from_model(i) for i in incidents]
    return schemas.IncidentListOut(incidents=out, count=len(out))


@router.get(
    "/{incident_id}",
    response_model=schemas.IncidentOut,
    summary="Get a single incident",
    description="Returns 404 if the incident does not exist.",
)
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    return schemas.IncidentOut.from_model(incident)


def _transition(incident_id: str, target_status: str, db: Session) -> schemas.IncidentOut:
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

    try:
        updated = incident_service.advance_status(db, incident, target_status)
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return schemas.IncidentOut.from_model(updated)


@router.post(
    "/{incident_id}/verify",
    response_model=schemas.IncidentOut,
    summary="Mark incident as Verified",
    description="Legal only when the incident is currently 'Detected'.",
)
def verify_incident(incident_id: str, db: Session = Depends(get_db)):
    return _transition(incident_id, "Verified", db)


@router.post(
    "/{incident_id}/alert",
    response_model=schemas.IncidentOut,
    summary="Mark incident as Alerted",
    description="Legal only when the incident is currently 'Verified'.",
)
def alert_incident(incident_id: str, db: Session = Depends(get_db)):
    return _transition(incident_id, "Alerted", db)


@router.post(
    "/{incident_id}/respond",
    response_model=schemas.IncidentOut,
    summary="Mark incident as Responding",
    description="Legal only when the incident is currently 'Alerted'.",
)
def respond_incident(incident_id: str, db: Session = Depends(get_db)):
    return _transition(incident_id, "Responding", db)


@router.post(
    "/{incident_id}/resolve",
    response_model=schemas.IncidentOut,
    summary="Mark incident as Resolved",
    description="Legal only when the incident is currently 'Responding'.",
)
def resolve_incident(incident_id: str, db: Session = Depends(get_db)):
    return _transition(incident_id, "Resolved", db)
