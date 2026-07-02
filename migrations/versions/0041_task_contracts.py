"""task contracts + reviewer registry + review reports (§13.1-13.3/§27.2/§12.3)

Revision ID: 0041
Revises: 0040
Create Date: 2026-07-02

Slice 42 — task contracts + maker-checker-verifier workflow + reviewer reports. Purely
additive: FIVE new tables (RLS ENABLE+FORCE + tenant_isolation on all).
  * task_contracts (SELECT/INSERT/UPDATE, no DELETE): §27.2 shape; guard = INSERT draft-only
    + bounded/non-blank JSONB text arrays + tools-disjoint + content frozen once not draft +
    the D-42-5 transition matrix + the draft→ready freeze prerequisites (≥1
    source_requirement link + 3-layer reviewer coverage) + the specialist_review→done
    DONE-GATE (option (b): EVERY registration's OWN latest review_reports verdict must be
    'approved' — a later same-layer approval never buries a standing rejection).
  * task_contract_artifact_links (SELECT/INSERT only): composite FK → intake_artifacts
    (existence) + a BEFORE-INSERT kind guard (link_kind → spine kind) + draft-only inserts.
  * task_contract_reviewers (SELECT/INSERT only): composite FK → agent_instances + the §2.2
    guard (reviewer's ACTUAL blueprint via instance→version must differ from the builder's)
    + draft-only inserts.
  * review_reports (SELECT/INSERT only — immutable): registration composite FK →
    task_contract_reviewers; can_merge GENERATED ALWAYS AS (verdict='approved') STORED
    (never caller-writable, V2-B2); approved⇒empty lists / rejected⇒failed+changes CHECKs;
    reportable-status window guard.
  * task_contract_events (SELECT/INSERT only): the transition trail; creation-duality CHECK
    ((from_status IS NULL) = (to_status='draft')).
Nothing here executes a review or flips any A5/readiness state.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_TRIM = r"E' \t\n\r\x0b\x0c'"

_STATUSES = (
    "draft",
    "ready_for_development",
    "in_progress",
    "specialist_review",
    "changes_requested",
    "done",
    "canceled",
    "superseded",
)
_LAYERS = ("role_specific", "cross_functional", "acceptance")
_VERDICTS = ("approved", "rejected_with_required_changes")
_RISKS = ("low", "medium", "high", "critical")
_LINK_KINDS = ("source_requirement", "acceptance_criterion", "test_oracle")

_APPEND_ONLY = (
    "task_contract_artifact_links",
    "task_contract_reviewers",
    "review_reports",
    "task_contract_events",
)


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _req(column: str, cap: int) -> str:
    return f"char_length({column}) BETWEEN 1 AND {cap} AND btrim({column}, {_TRIM}) <> ''"


def upgrade() -> None:
    # --- helper: a bounded, non-blank JSONB text array ------------------------------
    op.execute(
        f"""
        CREATE FUNCTION public.tc_text_array_ok(arr jsonb, max_items int, max_chars int)
        RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog AS $fn$
            SELECT jsonb_typeof(arr) = 'array'
               AND jsonb_array_length(arr) <= max_items
               AND NOT EXISTS (
                   SELECT 1 FROM jsonb_array_elements(arr) AS e(value)
                   WHERE jsonb_typeof(e.value) <> 'string'
                      OR char_length(e.value #>> '{{}}') < 1
                      OR char_length(e.value #>> '{{}}') > max_chars
                      OR btrim(e.value #>> '{{}}', {_TRIM}) = ''
               )
        $fn$
        """
    )

    # --- task_contracts ----------------------------------------------------------------
    op.create_table(
        "task_contracts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("task_ref", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("must_have", postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column(
            "must_not_do", postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column(
            "required_evidence", postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column(
            "definition_of_done", postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column(
            "allowed_tools", postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column(
            "forbidden_tools", postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column("risk_level", sa.Text(), nullable=False),
        sa.Column("builder_instance_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            _in("risk_level", _RISKS), name=op.f("ck_task_contracts_risk_level_valid")
        ),
        sa.CheckConstraint(_in("status", _STATUSES), name=op.f("ck_task_contracts_status_valid")),
        sa.CheckConstraint(_req("task_ref", 64), name=op.f("ck_task_contracts_task_ref_len")),
        sa.CheckConstraint(_req("title", 200), name=op.f("ck_task_contracts_title_len")),
        sa.CheckConstraint(
            _req("description", 4000), name=op.f("ck_task_contracts_description_len")
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["builder_instance_id", "project_id", "tenant_id"],
            ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"],
            name="builder_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_task_contracts_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_contracts")),
        sa.UniqueConstraint("tenant_id", "project_id", "task_ref", name="uq_task_contracts_ref"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_task_contracts_id_tenant"),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_task_contracts_id_project_tenant"
        ),
    )
    op.create_index(
        "ix_task_contracts_project_status", "task_contracts", ["tenant_id", "project_id", "status"]
    )

    # --- task_contract_artifact_links ----------------------------------------------------
    op.create_table(
        "task_contract_artifact_links",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("task_contract_id", sa.UUID(), nullable=False),
        sa.Column("artifact_id", sa.UUID(), nullable=False),
        sa.Column("link_kind", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            _in("link_kind", _LINK_KINDS),
            name=op.f("ck_task_contract_artifact_links_link_kind_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["task_contract_id", "project_id", "tenant_id"],
            ["task_contracts.id", "task_contracts.project_id", "task_contracts.tenant_id"],
            name="contract_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id", "project_id", "tenant_id"],
            ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"],
            name="artifact_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_tcal_tenant"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_contract_artifact_links")),
        sa.UniqueConstraint(
            "task_contract_id", "artifact_id", "link_kind", name="uq_tc_artifact_links_triple"
        ),
    )
    op.create_index(
        "ix_tc_artifact_links_contract",
        "task_contract_artifact_links",
        ["tenant_id", "task_contract_id"],
    )

    # --- task_contract_reviewers ---------------------------------------------------------
    op.create_table(
        "task_contract_reviewers",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("task_contract_id", sa.UUID(), nullable=False),
        sa.Column("reviewer_instance_id", sa.UUID(), nullable=False),
        sa.Column("layer", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            _in("layer", _LAYERS), name=op.f("ck_task_contract_reviewers_layer_valid")
        ),
        sa.ForeignKeyConstraint(
            ["task_contract_id", "project_id", "tenant_id"],
            ["task_contracts.id", "task_contracts.project_id", "task_contracts.tenant_id"],
            name="contract_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_instance_id", "project_id", "tenant_id"],
            ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"],
            name="reviewer_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_tcr_tenant"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_contract_reviewers")),
        sa.UniqueConstraint(
            "task_contract_id", "reviewer_instance_id", "layer", name="uq_tc_reviewers_triple"
        ),
        sa.UniqueConstraint(
            "task_contract_id",
            "reviewer_instance_id",
            "layer",
            "project_id",
            "tenant_id",
            name="uq_tc_reviewers_registration",
        ),
    )
    op.create_index(
        "ix_tc_reviewers_contract", "task_contract_reviewers", ["tenant_id", "task_contract_id"]
    )

    # --- review_reports --------------------------------------------------------------------
    op.create_table(
        "review_reports",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("task_contract_id", sa.UUID(), nullable=False),
        sa.Column("reviewer_instance_id", sa.UUID(), nullable=False),
        sa.Column("layer", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        # V2-B2 — GENERATED from the verdict; a supplied value is refused by Postgres.
        sa.Column(
            "can_merge",
            sa.Boolean(),
            sa.Computed("verdict = 'approved'", persisted=True),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "failed_criteria", postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column(
            "suspected_shortcuts",
            postgresql.JSONB(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "required_changes", postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "source_provenance",
            sa.Text(),
            server_default=sa.text("'caller_supplied_unverified'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(_in("verdict", _VERDICTS), name=op.f("ck_review_reports_verdict_valid")),
        sa.CheckConstraint(_in("layer", _LAYERS), name=op.f("ck_review_reports_layer_valid")),
        sa.CheckConstraint(
            "source_provenance IN ('caller_supplied_unverified')",
            name=op.f("ck_review_reports_source_provenance_valid"),
        ),
        sa.CheckConstraint(
            "verdict <> 'approved' OR (jsonb_array_length(failed_criteria) = 0 "
            "AND jsonb_array_length(suspected_shortcuts) = 0 "
            "AND jsonb_array_length(required_changes) = 0)",
            name=op.f("ck_review_reports_approved_lists_empty"),
        ),
        sa.CheckConstraint(
            "verdict <> 'rejected_with_required_changes' OR "
            "(jsonb_array_length(failed_criteria) >= 1 "
            "AND jsonb_array_length(required_changes) >= 1)",
            name=op.f("ck_review_reports_rejected_lists_required"),
        ),
        sa.CheckConstraint(_req("summary", 2000), name=op.f("ck_review_reports_summary_len")),
        sa.CheckConstraint(_req("source", 100), name=op.f("ck_review_reports_source_len")),
        sa.ForeignKeyConstraint(
            ["task_contract_id", "project_id", "tenant_id"],
            ["task_contracts.id", "task_contracts.project_id", "task_contracts.tenant_id"],
            name="contract_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_contract_id", "reviewer_instance_id", "layer", "project_id", "tenant_id"],
            [
                "task_contract_reviewers.task_contract_id",
                "task_contract_reviewers.reviewer_instance_id",
                "task_contract_reviewers.layer",
                "task_contract_reviewers.project_id",
                "task_contract_reviewers.tenant_id",
            ],
            name="registration",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_review_reports_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_reports")),
    )
    op.create_index(
        "ix_review_reports_contract_layer",
        "review_reports",
        ["tenant_id", "task_contract_id", "layer", "created_at"],
    )

    # --- task_contract_events -----------------------------------------------------------
    op.create_table(
        "task_contract_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("task_contract_id", sa.UUID(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"from_status IS NULL OR {_in('from_status', _STATUSES)}",
            name=op.f("ck_task_contract_events_from_status_valid"),
        ),
        sa.CheckConstraint(
            _in("to_status", _STATUSES), name=op.f("ck_task_contract_events_to_status_valid")
        ),
        sa.CheckConstraint(
            "(from_status IS NULL) = (to_status = 'draft')",
            name=op.f("ck_task_contract_events_creation_duality"),
        ),
        sa.CheckConstraint(_req("actor", 200), name=op.f("ck_task_contract_events_actor_len")),
        sa.ForeignKeyConstraint(
            ["task_contract_id", "project_id", "tenant_id"],
            ["task_contracts.id", "task_contracts.project_id", "task_contracts.tenant_id"],
            name="contract_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_tce_tenant"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_contract_events")),
    )
    op.create_index(
        "ix_tc_events_contract",
        "task_contract_events",
        ["tenant_id", "task_contract_id", "created_at"],
    )

    # --- guard: task_contracts (draft lock / matrix / freeze prereqs / DONE-GATE) --------
    op.execute(
        """
        CREATE FUNCTION public.task_contracts_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE
            layer_count int;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'draft' THEN
                    RAISE EXCEPTION 'task_contracts: must be created in draft';
                END IF;
                PERFORM public.tc_check_contract_arrays(NEW.must_have, NEW.must_not_do,
                    NEW.required_evidence, NEW.definition_of_done, NEW.allowed_tools,
                    NEW.forbidden_tools);
                RETURN NEW;
            END IF;

            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
               OR NEW.project_id IS DISTINCT FROM OLD.project_id
               OR NEW.builder_instance_id IS DISTINCT FROM OLD.builder_instance_id
               OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'task_contracts: identity/builder columns are immutable';
            END IF;

            IF NEW.status = OLD.status THEN
                IF OLD.status = 'draft' THEN
                    PERFORM public.tc_check_contract_arrays(NEW.must_have, NEW.must_not_do,
                        NEW.required_evidence, NEW.definition_of_done, NEW.allowed_tools,
                        NEW.forbidden_tools);
                    RETURN NEW;  -- draft content edits allowed
                END IF;
                IF public.tc_contract_content_differs(OLD, NEW) THEN
                    RAISE EXCEPTION 'task_contracts: content is immutable once not draft';
                END IF;
                RETURN NEW;  -- updated_at-only touch
            END IF;

            -- a transition row must not smuggle content changes
            IF public.tc_contract_content_differs(OLD, NEW) THEN
                RAISE EXCEPTION 'task_contracts: content is immutable on a transition';
            END IF;

            IF NOT (
                (OLD.status = 'draft' AND NEW.status IN ('ready_for_development', 'canceled'))
                OR (OLD.status = 'ready_for_development' AND NEW.status IN ('in_progress', 'canceled'))
                OR (OLD.status = 'in_progress' AND NEW.status IN ('specialist_review', 'canceled'))
                OR (OLD.status = 'specialist_review'
                    AND NEW.status IN ('changes_requested', 'done', 'canceled'))
                OR (OLD.status = 'changes_requested' AND NEW.status IN ('in_progress', 'canceled'))
                OR (OLD.status = 'done' AND NEW.status = 'superseded')
            ) THEN
                RAISE EXCEPTION 'task_contracts: illegal transition % -> %',
                    OLD.status, NEW.status;
            END IF;

            IF OLD.status = 'draft' AND NEW.status = 'ready_for_development' THEN
                IF NOT EXISTS (
                    SELECT 1 FROM public.task_contract_artifact_links l
                    WHERE l.task_contract_id = NEW.id AND l.link_kind = 'source_requirement'
                ) THEN
                    RAISE EXCEPTION 'task_contracts: freeze requires at least one '
                        'source_requirement link';
                END IF;
                SELECT count(DISTINCT r.layer) INTO layer_count
                FROM public.task_contract_reviewers r WHERE r.task_contract_id = NEW.id;
                IF layer_count < 3 THEN
                    RAISE EXCEPTION 'task_contracts: freeze requires reviewer coverage of '
                        'all 3 layers (got %)', layer_count;
                END IF;
            END IF;

            IF OLD.status = 'specialist_review' AND NEW.status = 'done' THEN
                -- DONE-GATE (option (b)): every registration's OWN latest verdict approved.
                PERFORM 1
                FROM public.task_contract_reviewers r
                LEFT JOIN LATERAL (
                    SELECT p.verdict FROM public.review_reports p
                    WHERE p.task_contract_id = r.task_contract_id
                      AND p.reviewer_instance_id = r.reviewer_instance_id
                      AND p.layer = r.layer
                    ORDER BY p.created_at DESC, p.id DESC
                    LIMIT 1
                ) latest ON true
                WHERE r.task_contract_id = NEW.id
                  AND (latest.verdict IS NULL OR latest.verdict <> 'approved')
                LIMIT 1;
                IF FOUND THEN
                    RAISE EXCEPTION 'task_contracts: done requires every registered '
                        'reviewer''s latest verdict approved (a pending or rejected '
                        'registration blocks done)';
                END IF;
            END IF;

            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.tc_check_contract_arrays(
            must_have jsonb, must_not_do jsonb, required_evidence jsonb,
            definition_of_done jsonb, allowed_tools jsonb, forbidden_tools jsonb
        ) RETURNS void LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            IF NOT (public.tc_text_array_ok(must_have, 32, 500)
                    AND public.tc_text_array_ok(must_not_do, 32, 500)
                    AND public.tc_text_array_ok(required_evidence, 32, 500)
                    AND public.tc_text_array_ok(definition_of_done, 32, 500)
                    AND public.tc_text_array_ok(allowed_tools, 64, 128)
                    AND public.tc_text_array_ok(forbidden_tools, 64, 128)) THEN
                RAISE EXCEPTION 'task_contracts: every text-list column must be an array '
                    'of bounded non-blank strings';
            END IF;
            IF EXISTS (
                SELECT 1 FROM jsonb_array_elements_text(allowed_tools) a(v)
                JOIN jsonb_array_elements_text(forbidden_tools) f(v) ON a.v = f.v
            ) THEN
                RAISE EXCEPTION 'task_contracts: allowed_tools and forbidden_tools overlap';
            END IF;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.tc_contract_content_differs(
            old_row public.task_contracts, new_row public.task_contracts
        ) RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog AS $fn$
            SELECT new_row.task_ref IS DISTINCT FROM old_row.task_ref
                OR new_row.title IS DISTINCT FROM old_row.title
                OR new_row.description IS DISTINCT FROM old_row.description
                OR new_row.must_have IS DISTINCT FROM old_row.must_have
                OR new_row.must_not_do IS DISTINCT FROM old_row.must_not_do
                OR new_row.required_evidence IS DISTINCT FROM old_row.required_evidence
                OR new_row.definition_of_done IS DISTINCT FROM old_row.definition_of_done
                OR new_row.allowed_tools IS DISTINCT FROM old_row.allowed_tools
                OR new_row.forbidden_tools IS DISTINCT FROM old_row.forbidden_tools
                OR new_row.risk_level IS DISTINCT FROM old_row.risk_level
        $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER task_contracts_guard BEFORE INSERT OR UPDATE ON public.task_contracts "
        "FOR EACH ROW EXECUTE FUNCTION public.task_contracts_guard()"
    )

    # --- guard: artifact links (draft-only + kind match) ---------------------------------
    op.execute(
        """
        CREATE FUNCTION public.task_contract_artifact_links_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE
            c_status text;
            a_kind text;
            expected text;
        BEGIN
            SELECT c.status INTO c_status FROM public.task_contracts c
            WHERE c.id = NEW.task_contract_id;
            IF c_status IS DISTINCT FROM 'draft' THEN
                RAISE EXCEPTION 'task_contract_artifact_links: contract must be draft '
                    '(links are freeze-locked), got %', c_status;
            END IF;
            SELECT a.kind INTO a_kind FROM public.intake_artifacts a
            WHERE a.id = NEW.artifact_id;
            expected := CASE NEW.link_kind
                WHEN 'source_requirement' THEN 'requirement'
                WHEN 'acceptance_criterion' THEN 'acceptance_criterion'
                WHEN 'test_oracle' THEN 'test_oracle'
            END;
            IF a_kind IS DISTINCT FROM expected THEN
                RAISE EXCEPTION 'task_contract_artifact_links: artifact kind mismatch '
                    '(link % requires %, got %)', NEW.link_kind, expected, a_kind;
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER task_contract_artifact_links_guard BEFORE INSERT "
        "ON public.task_contract_artifact_links "
        "FOR EACH ROW EXECUTE FUNCTION public.task_contract_artifact_links_guard()"
    )

    # --- guard: reviewers (draft-only + §2.2 blueprint distinctness) ----------------------
    op.execute(
        """
        CREATE FUNCTION public.task_contract_reviewers_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE
            c_status text;
            builder_bp uuid;
            reviewer_bp uuid;
        BEGIN
            SELECT c.status INTO c_status FROM public.task_contracts c
            WHERE c.id = NEW.task_contract_id;
            IF c_status IS DISTINCT FROM 'draft' THEN
                RAISE EXCEPTION 'task_contract_reviewers: contract must be draft '
                    '(reviewers are freeze-locked), got %', c_status;
            END IF;
            SELECT v.blueprint_id INTO builder_bp
            FROM public.task_contracts c
            JOIN public.agent_instances i ON i.id = c.builder_instance_id
            JOIN public.agent_versions v ON v.id = i.version_id
            WHERE c.id = NEW.task_contract_id;
            SELECT v.blueprint_id INTO reviewer_bp
            FROM public.agent_instances i
            JOIN public.agent_versions v ON v.id = i.version_id
            WHERE i.id = NEW.reviewer_instance_id;
            IF reviewer_bp = builder_bp THEN
                RAISE EXCEPTION 'task_contract_reviewers: reviewer cannot share the builder '
                    'blueprint (self-review, section 2.2)';
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER task_contract_reviewers_guard BEFORE INSERT "
        "ON public.task_contract_reviewers "
        "FOR EACH ROW EXECUTE FUNCTION public.task_contract_reviewers_guard()"
    )

    # --- guard: review_reports (reportable-status window + array shapes) ------------------
    op.execute(
        """
        CREATE FUNCTION public.review_reports_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE
            c_status text;
        BEGIN
            SELECT c.status INTO c_status FROM public.task_contracts c
            WHERE c.id = NEW.task_contract_id;
            IF c_status IS NULL
               OR c_status NOT IN ('in_progress', 'specialist_review', 'changes_requested') THEN
                RAISE EXCEPTION 'review_reports: contract status must be reportable '
                    '(in_progress/specialist_review/changes_requested), got %', c_status;
            END IF;
            IF NOT (public.tc_text_array_ok(NEW.failed_criteria, 32, 500)
                    AND public.tc_text_array_ok(NEW.suspected_shortcuts, 32, 500)
                    AND public.tc_text_array_ok(NEW.required_changes, 32, 500)) THEN
                RAISE EXCEPTION 'review_reports: every text-list column must be an array '
                    'of bounded non-blank strings';
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER review_reports_guard BEFORE INSERT ON public.review_reports "
        "FOR EACH ROW EXECUTE FUNCTION public.review_reports_guard()"
    )

    # --- append-only block triggers + RLS + grants -----------------------------------------
    for table in _APPEND_ONLY:
        op.execute(
            f"""
            CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
            LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
            BEGIN
                RAISE EXCEPTION '{table} is append-only (no UPDATE/DELETE/TRUNCATE in Slice 42)';
            END
            $fn$
            """
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON public.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.{table}_block_dml()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON public.{table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION public.{table}_block_dml()"
        )
    for table in ("task_contracts",) + _APPEND_ONLY:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT, UPDATE ON task_contracts TO uaid_app")
    for table in _APPEND_ONLY:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO uaid_app")


def downgrade() -> None:
    for table in ("task_contracts",) + _APPEND_ONLY:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in _APPEND_ONLY:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
    op.execute("DROP TRIGGER IF EXISTS review_reports_guard ON public.review_reports")
    op.execute("DROP FUNCTION IF EXISTS public.review_reports_guard()")
    op.execute(
        "DROP TRIGGER IF EXISTS task_contract_reviewers_guard ON public.task_contract_reviewers"
    )
    op.execute("DROP FUNCTION IF EXISTS public.task_contract_reviewers_guard()")
    op.execute(
        "DROP TRIGGER IF EXISTS task_contract_artifact_links_guard "
        "ON public.task_contract_artifact_links"
    )
    op.execute("DROP FUNCTION IF EXISTS public.task_contract_artifact_links_guard()")
    op.execute("DROP TRIGGER IF EXISTS task_contracts_guard ON public.task_contracts")
    op.execute("DROP FUNCTION IF EXISTS public.task_contracts_guard()")
    op.execute(
        "DROP FUNCTION IF EXISTS public.tc_contract_content_differs("
        "public.task_contracts, public.task_contracts)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS public.tc_check_contract_arrays("
        "jsonb, jsonb, jsonb, jsonb, jsonb, jsonb)"
    )
    op.drop_index("ix_tc_events_contract", table_name="task_contract_events")
    op.drop_table("task_contract_events")
    op.drop_index("ix_review_reports_contract_layer", table_name="review_reports")
    op.drop_table("review_reports")
    op.drop_index("ix_tc_reviewers_contract", table_name="task_contract_reviewers")
    op.drop_table("task_contract_reviewers")
    op.drop_index("ix_tc_artifact_links_contract", table_name="task_contract_artifact_links")
    op.drop_table("task_contract_artifact_links")
    op.drop_index("ix_task_contracts_project_status", table_name="task_contracts")
    op.drop_table("task_contracts")
    op.execute("DROP FUNCTION IF EXISTS public.tc_text_array_ok(jsonb, int, int)")
