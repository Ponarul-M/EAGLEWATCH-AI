"""
main.py

EagleWatch AI backend entrypoint.

Run locally with:
    uvicorn main:app --reload
"""

import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import Base, engine, SessionLocal
from services.incident_service import seed_if_empty
from routes import incidents, detection, analytics, ai

load_dotenv()

app = FastAPI(
    title="EagleWatch AI Backend",
    description=(
        "Backend for the EagleWatch AI public-safety monitoring dashboard. "
        "Provides incident management, a real YOLO + ByteTrack AI detection "
        "pipeline (/api/ai/*), a Demo Detection API that simulates the "
        "pipeline for reliable hackathon demos (/api/demo/detection), and "
        "dashboard/analytics data."
    ),
    version="1.1.0",
)

# ---------------------------------------------------------------------
# Sample CCTV/demo videos - served as static files so the Monitoring
# tab can play them directly, e.g. http://localhost:8000/sample_video/collision.mp4
# ---------------------------------------------------------------------

SAMPLE_VIDEO_DIR = os.path.join(
    os.path.dirname(__file__),
    "sample_video"
)

os.makedirs(SAMPLE_VIDEO_DIR, exist_ok=True)

app.mount(
    "/sample_video",
    StaticFiles(directory=SAMPLE_VIDEO_DIR),
    name="sample_video"
)

# ---------------------------------------------------------------------
# CORS - allow the Vite dev server to talk to this API
# ---------------------------------------------------------------------

_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
origins = [o.strip() for o in os.getenv("CORS_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------
# DB init + seed data (runs once on startup, never duplicates seed rows)
# ---------------------------------------------------------------------

Base.metadata.create_all(bind=engine)


@app.on_event("startup")
def on_startup():
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------

app.include_router(incidents.router)
app.include_router(detection.router)
app.include_router(analytics.router)
app.include_router(ai.router)


@app.get("/", tags=["Health"], summary="Health check")
def root():
    return {"status": "ok", "service": "EagleWatch AI Backend"}
