"""
routes/detection.py

Demo Detection API - simulates the AI/computer vision pipeline so the
full frontend workflow (Detected -> Verified -> Alerted -> Responding
-> Resolved) can be exercised end-to-end before real AI detection is
wired up.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import schemas
from services import incident_service

router = APIRouter(prefix="/api/demo", tags=["Demo Detection"])


@router.post(
    "/detection",
    response_model=schemas.IncidentOut,
    status_code=201,
    summary="Simulate an AI detection event",
    description=(
        "Creates a new incident with status 'Detected' using one of the "
        "canned demo scenarios (matching the frontend's AI Scenario "
        "Library): `collision`, `twowheeler`, `distress`. "
        "This is a placeholder for the real AI detection pipeline, which "
        "will replace this endpoint later - see services/detection_service.py."
    ),
)
def create_demo_detection(payload: schemas.DemoDetectionRequest, db: Session = Depends(get_db)):
    try:
        incident = incident_service.create_incident_from_scenario(db, payload.scenario)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return schemas.IncidentOut.from_model(incident)


@router.get(
    "/scenarios",
    summary="List available demo scenarios",
    description="Convenience endpoint so the frontend can build its "
                "scenario picker directly from backend data instead of "
                "duplicating it in JS.",
)
def list_scenarios():
    return {
        scenario_id: {k: v for k, v in scenario.items()}
        for scenario_id, scenario in incident_service.SCENARIOS.items()
    }
