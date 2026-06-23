"""SQLAlchemy ORM models + Pydantic schemas."""
import uuid
from datetime import datetime
from typing import Literal, Optional

from pgvector.sqlalchemy import Vector
from pydantic import BaseModel
from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, String, Text, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base

# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------

Verdict = Literal["verified", "false", "misleading"]
CheckStatus = Literal["pending", "extracting", "transcribing", "analyzing", "verifying", "done", "failed"]


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    plan = Column(String(20), nullable=False, default="free")  # free | monthly | yearly
    checks_used = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    checks = relationship("Check", back_populates="user", lazy="select")


class Check(Base):
    """One fact-check job submitted by a user."""
    __tablename__ = "checks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    url = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    verdict = Column(String(20), nullable=True)  # overall verdict after all claims resolved
    error = Column(Text, nullable=True)
    # Raw content from extractor
    caption = Column(Text, nullable=True)
    transcript = Column(Text, nullable=True)
    platform = Column(String(40), nullable=True)
    author_handle = Column(String(120), nullable=True)
    score = Column(Float, nullable=True)  # 0.0–1.0 truth score derived from claim confidences
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="checks")
    claims = relationship("Claim", back_populates="check", cascade="all, delete-orphan")


class Claim(Base):
    """A single factual claim extracted from a Check."""
    __tablename__ = "claims"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    check_id = Column(UUID(as_uuid=True), ForeignKey("checks.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    verdict = Column(String(20), nullable=True)
    confidence = Column(Float, nullable=True)  # 0.0 – 1.0
    reasoning = Column(Text, nullable=True)
    # pgvector embedding for similarity matching (text-embedding-3-small = 1536 dims)
    embedding = Column(Vector(1536), nullable=True)

    check = relationship("Check", back_populates="claims")
    sources = relationship("Source", back_populates="claim", cascade="all, delete-orphan")


class Source(Base):
    """A web source that supports or contradicts a Claim."""
    __tablename__ = "sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=True)
    url = Column(Text, nullable=False)
    snippet = Column(Text, nullable=True)
    # whether this source supports, contradicts, or is neutral toward the claim
    stance = Column(String(20), nullable=True)  # supports | contradicts | neutral
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    claim = relationship("Claim", back_populates="sources")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    plan: str
    checks_used: float

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CheckCreate(BaseModel):
    url: str


class SourceOut(BaseModel):
    id: str
    title: Optional[str]
    url: str
    snippet: Optional[str]
    stance: Optional[str]

    model_config = {"from_attributes": True}


class ClaimOut(BaseModel):
    id: str
    text: str
    verdict: Optional[str]
    confidence: Optional[float]
    reasoning: Optional[str]
    sources: list[SourceOut] = []

    model_config = {"from_attributes": True}


class CheckOut(BaseModel):
    id: str
    url: str
    status: str
    verdict: Optional[str]
    score: Optional[float]
    error: Optional[str]
    caption: Optional[str]
    transcript: Optional[str]
    platform: Optional[str]
    author_handle: Optional[str]
    created_at: datetime
    claims: list[ClaimOut] = []

    model_config = {"from_attributes": True}
