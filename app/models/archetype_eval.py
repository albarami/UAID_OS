"""``archetype_evals`` — the GLOBAL, admin-curated controlled eval library (Slice 40, §9.5.1).

One row per (archetype, eval_version): the §9.5.1 methodology (representative tasks / gold-oracle source /
scoring rubric), the **minimum activation threshold**, the zero-critical rule, the required case
categories (positive/negative/edge/adversarial/incomplete), and the refresh policy. GLOBAL (not RLS) —
``uaid_app`` SELECT-only, migration-seeded; immutable append-only (a new version is a new row, never an
UPDATE). The ``archetype`` CHECK + the 11 seeded rows live in migration ``0039`` (self-contained).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ArchetypeEval(Base):
    __tablename__ = "archetype_evals"
    __table_args__ = (
        CheckConstraint(
            "min_aggregate_score >= 0 AND min_aggregate_score <= 1",
            name="min_aggregate_score_range",
        ),
        CheckConstraint("min_cases >= 1", name="min_cases_positive"),
        UniqueConstraint("archetype", "eval_version", name="uq_archetype_evals_archetype_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    archetype: Mapped[str] = mapped_column(Text, nullable=False)
    eval_version: Mapped[str] = mapped_column(Text, nullable=False)
    representative_task_set: Mapped[list] = mapped_column(JSONB, nullable=False)
    gold_answer_source: Mapped[list] = mapped_column(JSONB, nullable=False)
    scoring_rubric: Mapped[list] = mapped_column(JSONB, nullable=False)
    min_aggregate_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    require_zero_critical: Mapped[bool] = mapped_column(Boolean, nullable=False)
    min_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    required_categories: Mapped[list] = mapped_column(JSONB, nullable=False)
    refresh_policy: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
