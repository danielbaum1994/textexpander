"""SQLAlchemy models and database setup."""

from __future__ import annotations

import os

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, create_engine, func, text
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker


DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./textexpander.db")

# Log the raw URL scheme for debugging (not the full URL to avoid leaking creds)
print(f"[database] Raw DATABASE_URL starts with: {DATABASE_URL[:20]}...")

# Normalize to a valid SQLAlchemy URL
DATABASE_URL = DATABASE_URL.strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
elif not DATABASE_URL.startswith(("postgresql://", "sqlite://")):
    # Unknown scheme — try forcing postgresql://
    from urllib.parse import urlparse
    parsed = urlparse(DATABASE_URL)
    DATABASE_URL = f"postgresql://{parsed.netloc}{parsed.path}"
    if parsed.query:
        DATABASE_URL += f"?{parsed.query}"

print(f"[database] Final DATABASE_URL starts with: {DATABASE_URL[:25]}...")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    google_id = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    api_key = Column(String, unique=True, index=True)
    paused = Column(Boolean, default=False, server_default="false")
    created_at = Column(DateTime, server_default=func.now())

    snippets = relationship("Snippet", back_populates="user", cascade="all, delete-orphan")


class Snippet(Base):
    __tablename__ = "snippets"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    abbreviation = Column(String, nullable=False)
    expansion = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="snippets")


def create_tables():
    Base.metadata.create_all(bind=engine)
    # Migrate: add paused column if it doesn't exist
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN paused BOOLEAN DEFAULT false"))
            conn.commit()
        except Exception:
            conn.rollback()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
