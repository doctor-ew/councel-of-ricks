"""SQLAlchemy ORM models."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, ARRAY
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    type_annotation_map = {
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
    }


class Document(Base):
    """Document metadata."""

    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    document_type: Mapped[str | None] = mapped_column(String(50), default="other")
    deponent_name: Mapped[str | None] = mapped_column(String(200))
    total_pages: Mapped[int | None] = mapped_column(Integer)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete")


class Chunk(Base):
    """Document chunk with embedding."""

    __tablename__ = "chunks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), default="text")
    embedding = mapped_column(Vector(1536))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="chunks")


class WitnessProfile(Base):
    """Witness profile for tailored questioning."""

    __tablename__ = "witness_profiles"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # plaintiff, defendant, witness, expert
    relationship_to_case: Mapped[str] = mapped_column(Text, nullable=False)
    knowledge_areas: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    limitations: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    agent_intensity: Mapped[int] = mapped_column(Integer, default=5)  # 1-10 scale
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sessions: Mapped[list["Session"]] = relationship(back_populates="profile")
    familiar_documents: Mapped[list["ProfileDocument"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class ProfileDocument(Base):
    """Junction table for documents a witness is familiar with."""

    __tablename__ = "profile_documents"

    profile_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("witness_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    familiarity_level: Mapped[str] = mapped_column(
        String(50), default="familiar"
    )  # authored, familiar, mentioned

    # Relationships
    profile: Mapped["WitnessProfile"] = relationship(back_populates="familiar_documents")
    document: Mapped["Document"] = relationship()


class Session(Base):
    """Preparation session."""

    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    witness_name: Mapped[str] = mapped_column(String(200), nullable=False)
    profile_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("witness_profiles.id"), nullable=True
    )
    agent_mode: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(50), default="active")
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Relationships
    profile: Mapped["WitnessProfile | None"] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(back_populates="session", cascade="all, delete")
    facts: Mapped[list["FactLedger"]] = relationship(back_populates="session", cascade="all, delete")


class Message(Base):
    """Chat message."""

    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    arbiter_flags: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    truth_score: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    session: Mapped["Session"] = relationship(back_populates="messages")


class FactLedger(Base):
    """Fact tracking ledger."""

    __tablename__ = "fact_ledger"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    fact_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_message_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id"))
    citations: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    contradicts: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    superseded_by: Mapped[UUID | None] = mapped_column(ForeignKey("fact_ledger.id"))

    # Relationships
    session: Mapped["Session"] = relationship(back_populates="facts")
