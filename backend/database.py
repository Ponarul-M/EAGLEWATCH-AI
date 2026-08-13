"""
database.py

SQLAlchemy engine / session setup for EagleWatch AI.

Uses SQLite so the whole backend can run locally with zero external
infrastructure - perfect for a hackathon.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./eaglewatch.db")

# check_same_thread=False is required for SQLite when it's accessed
# from multiple threads (FastAPI's default threadpool for sync routes).
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
