"""SQLAlchemy models and database setup."""

from __future__ import annotations

import os

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker


DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./textexpander.db")

# Railway may provide various URL formats; SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
elif DATABASE_URL.startswith("https://"):
    DATABASE_URL = DATABASE_URL.replace("https://", "postgresql://", 1)
elif DATABASE_URL.startswith("http://"):
    DATABASE_URL = DATABASE_URL.replace("http://", "postgresql://", 1)

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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
