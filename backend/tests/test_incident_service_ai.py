from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Incident
from services import incident_service


def _memory_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_create_incident_from_ai_populates_required_frontend_fields():
    db = _memory_db()
    incident = incident_service.create_incident_from_ai(
        db,
        category="accident",
        label="Vehicle Collision",
        sub="Possible multi-vehicle collision detected",
        camera_id="CAM-01",
        confidence=93,
        severity="critical",
    )

    assert incident.id.startswith("INC-")
    assert incident.category == "accident"
    assert incident.label == "Vehicle Collision"
    assert incident.status == "Detected"
    assert incident.camera_id == "CAM-01"
    assert incident.confidence == 93
    assert incident.severity == "critical"
    # location/x/y come from configured camera metadata, not GPS
    assert incident.location
    assert incident.x is not None
    assert incident.y is not None

    # Round-trips through the DB correctly
    fetched = db.query(Incident).filter(Incident.id == incident.id).first()
    assert fetched is not None
    assert fetched.label == "Vehicle Collision"


def test_create_incident_from_ai_clamps_confidence_to_0_100():
    db = _memory_db()
    incident = incident_service.create_incident_from_ai(
        db, category="safety", label="Person Distress", sub="x",
        camera_id="CAM-01", confidence=150, severity="high",
    )
    assert incident.confidence == 100

    incident2 = incident_service.create_incident_from_ai(
        db, category="safety", label="Person Distress", sub="x",
        camera_id="CAM-01", confidence=-5, severity="high",
    )
    assert incident2.confidence == 0
