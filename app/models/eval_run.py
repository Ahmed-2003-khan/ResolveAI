import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    git_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    total_cases: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    groundedness: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    helpfulness: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    policy_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    results: Mapped[list["EvalResult"]] = relationship(back_populates="run")


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_runs.id"), nullable=False
    )
    case_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    actual_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_scores: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    run: Mapped["EvalRun"] = relationship(back_populates="results")
