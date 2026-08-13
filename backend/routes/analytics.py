"""
routes/analytics.py

Aggregated analytics for the frontend's Analytics view (incidents by
type, by severity, high-risk locations, response-time info).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
import schemas
from services import incident_service

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get(
    "",
    response_model=schemas.AnalyticsOut,
    summary="Analytics data",
    description="Returns incidents-by-type, incidents-by-severity, "
                "high-risk locations, average response time, and the "
                "most recent incidents for trend display.",
)
def get_analytics(db: Session = Depends(get_db)):
    data = incident_service.compute_analytics(db)
    data["recent_incidents"] = [
        schemas.IncidentOut.from_model(i) for i in data["recent_incidents"]
    ]
    return data
