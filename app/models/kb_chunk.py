import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KBChunk(Base):
    __tablename__ = "kb_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_tsv: Mapped[Any] = mapped_column(TSVECTOR, nullable=True)
    # Language-agnostic full-text vector for Roman-Urdu BM25. Generated/stored
    # by Postgres — never inserted by the ORM.
    content_tsv_simple: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', content)", persisted=True),
        nullable=True,
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    product_area: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidentiality: Mapped[str] = mapped_column(String(20), default="public")
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
