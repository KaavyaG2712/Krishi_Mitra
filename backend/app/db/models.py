from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Computed, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    __table_args__ = (UniqueConstraint("module", "version", name="uq_model_registry_module_version"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    module: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(128))
    dataset_version: Mapped[str] = mapped_column(String(128))
    metrics_json: Mapped[dict] = mapped_column(JSONB)
    artifact_location: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DiseaseScan(Base):
    __tablename__ = "disease_scans"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    image_reference: Mapped[str] = mapped_column(String(80), index=True)
    crop_hint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    crop_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    predicted_label: Mapped[str] = mapped_column(String(128))
    confidence: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(512))
    publisher: Mapped[str] = mapped_column(String(256))
    source_url: Mapped[str] = mapped_column(String(2048))
    licence: Mapped[str | None] = mapped_column(String(256), nullable=True)
    checksum: Mapped[str] = mapped_column(String(128), unique=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_text: Mapped[str] = mapped_column(Text)
    # Legacy vector columns remain nullable for existing deployments; local
    # text retrieval does not create or consume embeddings.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, coalesce(chunk_text, ''::text))", persisted=True),
    )


class AdvisorConversation(Base):
    __tablename__ = "advisor_conversations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdvisorMessage(Base):
    __tablename__ = "advisor_messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("advisor_conversations.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    abstained: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[float] = mapped_column(Float)
    generation_model: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdvisorCitation(Base):
    __tablename__ = "advisor_citations"
    __table_args__ = (UniqueConstraint("message_id", "rank", name="uq_advisor_citation_message_rank"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(ForeignKey("advisor_messages.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="RESTRICT"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    similarity_score: Mapped[float] = mapped_column(Float)
