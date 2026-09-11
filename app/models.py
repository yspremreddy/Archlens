"""SQLAlchemy ORM models mirroring docs/SCHEMA.md exactly.

docs/SCHEMA.md is the design source of truth; this module and the Alembic
migration in alembic/versions/ are its implementation. If they ever
diverge, SCHEMA.md should be updated deliberately (per engineering guideline 9),
not silently outpaced by the code.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import get_settings
from app.db import Base

_settings = get_settings()


def _uuid_pk():
    # A fresh mapped_column() per call — SQLAlchemy Column objects cannot
    # be shared across multiple Table/mapped classes.
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def _created_at_col():
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _updated_at_col():
    return mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("source_type IN ('upload')", name="ck_documents_source_type"),
        CheckConstraint("file_size_bytes >= 0", name="ck_documents_file_size_nonneg"),
        CheckConstraint(
            "status IN ('pending','ingested','failed')", name="ck_documents_status"
        ),
        Index("idx_documents_status", "status"),
        Index("idx_documents_content_hash", "content_hash"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="upload")
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(Text)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at_col()
    updated_at: Mapped[datetime] = _updated_at_col()

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_chunk_index"),
        CheckConstraint("chunk_index >= 0", name="ck_chunks_chunk_index_nonneg"),
        CheckConstraint("length(text) > 0", name="ck_chunks_text_nonempty"),
        Index("idx_chunks_document_id", "document_id"),
        Index("idx_chunks_content_hash", "content_hash"),
        # Phase 2: lexical (full-text) search index. A functional GIN index
        # over to_tsvector(...) rather than a stored generated column —
        # avoids keeping a second column in sync and Postgres can still use
        # the index as long as queries use the identical expression.
        Index(
            "idx_chunks_text_fts",
            text("to_tsvector('english', text)"),
            postgresql_using="gin",
        ),
        # Phase 2: ANN index for vector similarity, deferred in Phase 1
        # (see docs/SCHEMA.md §2) until there was a retrieval query to tune
        # it against. HNSW (not ivfflat) — no training/list-count tuning
        # needed and pgvector 0.8 (bundled in pgvector/pgvector:pg16)
        # supports it natively; cosine ops to match the cosine distance
        # used in vector_search (app/retrieval/vector.py).
        Index(
            "idx_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # Phase 6: multimodal chunks share this same table (see module
        # docstring update in docs/SCHEMA.md §2 and docs/DECISIONS.md
        # ADR-008) — a text chunk from OCR or a vision-model caption is
        # still just a Chunk, searchable by the exact same hybrid/vector/
        # lexical retrieval with zero retrieval-layer changes.
        CheckConstraint(
            "modality IN ('text','image_ocr','image_caption')", name="ck_chunks_modality"
        ),
        Index("idx_chunks_modality", "modality"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(_settings.embedding_dimension), nullable=True)
    modality: Mapped[str] = mapped_column(Text, nullable=False, server_default="text")
    bbox: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at_col()

    document: Mapped["Document"] = relationship(back_populates="chunks")


class Component(Base):
    __tablename__ = "components"
    __table_args__ = (
        CheckConstraint(
            "type IN ('service','datastore','queue','external_system','other')",
            name="ck_components_type",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL")
    )
    extraction_method: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="manual"
    )
    created_at: Mapped[datetime] = _created_at_col()
    updated_at: Mapped[datetime] = _updated_at_col()

    __table_args__ = __table_args__ + (
        CheckConstraint(
            "extraction_method IN ('manual','llm_extracted','rule_based','vision_extracted')",
            name="ck_components_extraction_method",
        ),
        Index("idx_components_type", "type"),
        Index("idx_components_source_document_id", "source_document_id"),
        Index("idx_components_tags", "tags", postgresql_using="gin"),
    )


class ComplianceControl(Base):
    __tablename__ = "compliance_controls"
    __table_args__ = (
        UniqueConstraint("framework", "control_code", name="uq_compliance_controls_framework_code"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    framework: Mapped[str] = mapped_column(Text, nullable=False, server_default="archlens-custom")
    control_code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at_col()
    updated_at: Mapped[datetime] = _updated_at_col()


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open','resolved','dismissed')", name="ck_findings_status"
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_findings_confidence_range",
        ),
        # Phase 7: policy-engine verdicts (app/policy/). Nullable — a
        # Phase 3 /answer finding has no verdict/severity (it's a free-
        # text answer, not a policy check), so existing rows and the
        # existing /answer code path are unaffected.
        CheckConstraint(
            "verdict IS NULL OR verdict IN ('PASS','FAIL','UNKNOWN','CONFLICT')",
            name="ck_findings_verdict",
        ),
        CheckConstraint(
            "severity IS NULL OR severity IN ('low','medium','high','critical')",
            name="ck_findings_severity",
        ),
        Index("idx_findings_status", "status"),
        Index("idx_findings_control_id", "control_id"),
        Index("idx_findings_component_id", "component_id"),
        Index("idx_findings_verdict", "verdict"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(Text, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    verdict: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(Text)
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compliance_controls.id", ondelete="RESTRICT")
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL")
    )
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at_col()
    updated_at: Mapped[datetime] = _updated_at_col()

    evidence: Mapped[list["FindingEvidence"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )


class FindingEvidence(Base):
    __tablename__ = "finding_evidence"
    __table_args__ = (
        UniqueConstraint("finding_id", "chunk_id", name="uq_finding_evidence_finding_chunk"),
        Index("idx_finding_evidence_finding_id", "finding_id"),
        Index("idx_finding_evidence_chunk_id", "chunk_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="RESTRICT"), nullable=False
    )
    relevance_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at_col()

    finding: Mapped["Finding"] = relationship(back_populates="evidence")


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_log_entity", "entity_type", "entity_id"),
        Index("idx_audit_log_event_type", "event_type"),
        Index("idx_audit_log_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at_col()
