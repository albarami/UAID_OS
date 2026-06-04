"""runtime_events

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-04

Slice 8b: expand the run_steps.event_type CHECK to include the runtime-integration
events (blocked_on_approval / retried / cost_paused). No tables/columns/grants change.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Bare token; the ck naming convention renders it to ck_run_steps_event_type_valid.
_CONSTRAINT = "event_type_valid"
_OLD = (
    "event_type IN ('run_started', 'step_completed', 'run_resumed', 'run_completed', 'run_failed')"
)
_NEW = (
    "event_type IN ('run_started', 'step_completed', 'run_resumed', 'run_completed', "
    "'run_failed', 'blocked_on_approval', 'retried', 'cost_paused')"
)


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "run_steps", type_="check")
    op.create_check_constraint(_CONSTRAINT, "run_steps", _NEW)


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "run_steps", type_="check")
    op.create_check_constraint(_CONSTRAINT, "run_steps", _OLD)
