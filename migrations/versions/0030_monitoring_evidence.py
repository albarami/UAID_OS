"""monitoring_evidence (monitoring_status_snapshots)

Revision ID: 0030
Revises: 0029
Create Date: 2026-06-25

Slice 31 — monitoring / alerts evidence connector (App. B #11 / §26.3 / §26.6). Adds the tenant-owned,
**immutable append-only** ``monitoring_status_snapshots`` (RLS; SELECT/INSERT only — no
UPDATE/DELETE/TRUNCATE; provider/provenance/failure_kind enums; an HTTPS-URL ``target_ref`` shape +
char-class + length + token-denylist CHECK; ``observed_http_status`` 100..599-or-NULL; counts
0..32767-or-NULL [B7]; the ``overall_active = (monitoring_active AND alerts_active)`` invariant; and the
**read-state honesty CHECK** [B4/B6] — a valid read requires 200 + non-null counts + consistent
active-booleans, a failed read requires a ``failure_kind`` + NULL counts, with per-``failure_kind``
read-state, NULL-safe via ``IS [NOT] DISTINCT FROM``; plus UPDATE/DELETE/TRUNCATE block triggers). All
validation is expressible as column CHECKs, so there is no BEFORE INSERT guard trigger. **Additive — no
change to existing tables.** Mirrors the append-only snapshot pattern of ``0025``/``0028``/``0029``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_TABLE = "monitoring_status_snapshots"

# Read-state honesty invariant (B4/B6), NULL-safe so an inconsistent row is FALSE (not NULL, which a
# CHECK would silently pass).
_READ_STATE_CK = """
(
  (response_valid AND provider_reachable
   AND observed_http_status IS NOT DISTINCT FROM 200 AND failure_kind IS NULL
   AND active_monitor_count IS NOT NULL AND active_alert_rule_count IS NOT NULL
   AND monitoring_active = (active_monitor_count >= 1)
   AND alerts_active = (active_alert_rule_count >= 1))
  OR
  (NOT response_valid AND failure_kind IS NOT NULL
   AND active_monitor_count IS NULL AND active_alert_rule_count IS NULL
   AND NOT monitoring_active AND NOT alerts_active
   AND (
     (failure_kind = 'unreachable' AND NOT provider_reachable AND observed_http_status IS NULL)
     OR (failure_kind = 'http_error' AND provider_reachable
         AND observed_http_status IS NOT NULL AND observed_http_status IS DISTINCT FROM 200)
     OR (failure_kind IN ('content_type','oversize','malformed') AND provider_reachable
         AND observed_http_status IS NOT DISTINCT FROM 200)
   ))
)
""".strip()


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("target_ref", sa.Text(), nullable=False),
        sa.Column("provider_reachable", sa.Boolean(), nullable=False),
        sa.Column("response_valid", sa.Boolean(), nullable=False),
        sa.Column("observed_http_status", sa.SmallInteger(), nullable=True),
        sa.Column("failure_kind", sa.Text(), nullable=True),
        sa.Column("active_monitor_count", sa.SmallInteger(), nullable=True),
        sa.Column("active_alert_rule_count", sa.SmallInteger(), nullable=True),
        sa.Column("monitoring_active", sa.Boolean(), nullable=False),
        sa.Column("alerts_active", sa.Boolean(), nullable=False),
        sa.Column("overall_active", sa.Boolean(), nullable=False),
        sa.Column(
            "provenance",
            sa.Text(),
            server_default=sa.text("'caller_supplied_unverified'"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provenance IN ('caller_supplied_unverified','connector_verified')",
            name=op.f("ck_mss_provenance_valid"),
        ),
        sa.CheckConstraint(
            "provider IN ('generic_monitoring_api')", name=op.f("ck_mss_provider_valid")
        ),
        sa.CheckConstraint("target_ref ~ '^https://'", name=op.f("ck_mss_target_ref_https")),
        sa.CheckConstraint("target_ref !~ '[[:space:]@?#]'", name=op.f("ck_mss_target_ref_chars")),
        sa.CheckConstraint(
            "char_length(target_ref) BETWEEN 1 AND 2048", name=op.f("ck_mss_target_ref_len")
        ),
        sa.CheckConstraint(
            "target_ref !~* '(gh[opusr]_|github_pat_)'", name=op.f("ck_mss_target_ref_not_tokenish")
        ),
        sa.CheckConstraint(
            "observed_http_status IS NULL OR (observed_http_status BETWEEN 100 AND 599)",
            name=op.f("ck_mss_http_status_range"),
        ),
        sa.CheckConstraint(
            "failure_kind IS NULL OR failure_kind IN "
            "('unreachable','http_error','content_type','oversize','malformed')",
            name=op.f("ck_mss_failure_kind_valid"),
        ),
        sa.CheckConstraint(
            "active_monitor_count IS NULL OR (active_monitor_count BETWEEN 0 AND 32767)",
            name=op.f("ck_mss_monitor_count_range"),
        ),
        sa.CheckConstraint(
            "active_alert_rule_count IS NULL OR (active_alert_rule_count BETWEEN 0 AND 32767)",
            name=op.f("ck_mss_alert_count_range"),
        ),
        sa.CheckConstraint(
            "overall_active = (monitoring_active AND alerts_active)",
            name=op.f("ck_mss_overall_invariant"),
        ),
        sa.CheckConstraint(_READ_STATE_CK, name=op.f("ck_mss_read_state")),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_monitoring_status_snapshots_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monitoring_status_snapshots")),
    )
    op.create_index(
        "ix_mss_tenant_project_target_created",
        _TABLE,
        ["tenant_id", "project_id", "provider", "target_ref", "created_at"],
    )

    # --- append-only: block UPDATE/DELETE/TRUNCATE (mirror 0029) -------------------
    op.execute(
        """
        CREATE FUNCTION public.monitoring_status_snapshots_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'monitoring_status_snapshots is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER monitoring_status_snapshots_no_update_delete
            BEFORE UPDATE OR DELETE ON public.{_TABLE}
            FOR EACH ROW EXECUTE FUNCTION public.monitoring_status_snapshots_block_mutation()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER monitoring_status_snapshots_no_truncate
            BEFORE TRUNCATE ON public.{_TABLE}
            FOR EACH STATEMENT EXECUTE FUNCTION public.monitoring_status_snapshots_block_mutation()
        """
    )

    # --- RLS + grants (mirror 0029) -----------------------------------------------
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {_TABLE} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {_TABLE} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON {_TABLE} TO uaid_app")


def downgrade() -> None:
    op.execute(f"REVOKE ALL ON {_TABLE} FROM uaid_app")
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {_TABLE}")
    op.execute(f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
    op.execute(f"DROP TRIGGER IF EXISTS monitoring_status_snapshots_no_truncate ON public.{_TABLE}")
    op.execute(
        f"DROP TRIGGER IF EXISTS monitoring_status_snapshots_no_update_delete ON public.{_TABLE}"
    )
    op.execute("DROP FUNCTION IF EXISTS public.monitoring_status_snapshots_block_mutation()")
    op.drop_index("ix_mss_tenant_project_target_created", table_name=_TABLE)
    op.drop_table(_TABLE)
