"""connector-observed staging rollback verification evidence

Revision ID: 0051
Revises: 0050
Create Date: 2026-07-13

Slice 52. Additive-only: two tenant-owned RLS ENABLE+FORCE append-only tables and one
composite identity target on deployment_target_snapshots. Existing deployment semantics,
release findings guards, readiness, and no-go reasons are unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_RAW_HASH = r"^[0-9a-f]{64}$"
_PACK_HASH = r"^sha256:[0-9a-f]{64}$"
_RUNNER_HASH = "73064081141351425c245a6f8bcbe5c6427f130c9a0bf5f8c0aee991ad0a3e53"


def _append_only(table: str) -> None:
    op.execute(
        f"""
        CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN RAISE EXCEPTION '{table} is append-only'; END $fn$
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


def _tenant_table(table: str) -> None:
    _append_only(table)
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON public.{table} "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON public.{table} TO uaid_app")


def _create_runs() -> None:
    op.create_table(
        "rollback_verification_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=False),
        sa.Column("evidence_pack_id", sa.UUID(), nullable=False),
        sa.Column("staging_target_snapshot_id", sa.UUID(), nullable=True),
        sa.Column("drill_contract_version", sa.Text(), nullable=False),
        sa.Column("verification_contract_version", sa.Text(), nullable=False),
        sa.Column("staging_target_contract_version", sa.Text(), nullable=False),
        sa.Column("artifact_provenance", sa.Text(), nullable=False),
        sa.Column("execution_observation", sa.Text(), nullable=False),
        sa.Column("repo_binding_hash", sa.Text(), nullable=False),
        sa.Column("commit_sha", sa.Text(), nullable=False),
        sa.Column("core_content_hash", sa.Text(), nullable=False),
        sa.Column("artifact_scope_digest", sa.Text(), nullable=False),
        sa.Column("issue_binding_digest", sa.Text(), nullable=False),
        sa.Column("source_set_digest", sa.Text(), nullable=False),
        sa.Column("traceability_digest", sa.Text(), nullable=False),
        sa.Column("staging_target_binding_hash", sa.Text(), nullable=False),
        sa.Column("staging_snapshot_digest", sa.Text(), nullable=True),
        sa.Column("from_artifact_digest", sa.Text(), nullable=True),
        sa.Column("to_artifact_digest", sa.Text(), nullable=True),
        sa.Column("runner_manifest_hash", sa.Text(), nullable=False),
        sa.Column("provider_run_ref_hash", sa.Text(), nullable=True),
        sa.Column("artifact_content_hash", sa.Text(), nullable=True),
        sa.Column("workflow_conclusion", sa.Text(), nullable=True),
        sa.Column("attempt_status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("phase_count", sa.SmallInteger(), nullable=False),
        sa.Column("phase_digest", sa.Text(), nullable=True),
        sa.Column("drill_result", sa.Text(), nullable=False),
        sa.Column("evidence_consistent", sa.Boolean(), nullable=False),
        sa.Column("gate_eligible", sa.Boolean(), nullable=False),
        sa.Column("scope_limitation_code", sa.Text(), nullable=False),
        sa.Column("artifact_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "drill_contract_version='slice52.rollback_drill.v1' AND "
            "verification_contract_version='slice52.rollback_verification.v1' AND "
            "staging_target_contract_version='slice52.staging_target.v1'",
            name="ck_rollback_verification_runs_contracts",
        ),
        sa.CheckConstraint(
            "artifact_provenance IN ('connector_verified_ci_rollback','no_artifact') AND "
            "execution_observation IN ('connector_observed_ci','connector_observation_failed')",
            name="ck_rollback_verification_runs_provenance",
        ),
        sa.CheckConstraint(
            "attempt_status IN ('succeeded','failed','refused')",
            name="ck_rollback_verification_runs_attempt_status",
        ),
        sa.CheckConstraint(
            "workflow_conclusion IS NULL OR workflow_conclusion IN "
            "('success','failure','cancelled','timed_out','action_required')",
            name="ck_rollback_verification_runs_workflow_conclusion",
        ),
        sa.CheckConstraint(
            "drill_result IN ('passed','failed','incomplete')",
            name="ck_rollback_verification_runs_drill_result",
        ),
        sa.CheckConstraint(
            f"repo_binding_hash ~ '{_PACK_HASH}' AND commit_sha ~ '^[0-9a-f]{{40}}$' AND "
            f"core_content_hash ~ '{_PACK_HASH}' AND artifact_scope_digest ~ '{_PACK_HASH}' AND "
            f"issue_binding_digest ~ '{_PACK_HASH}' AND source_set_digest ~ '{_PACK_HASH}' AND "
            f"traceability_digest ~ '{_PACK_HASH}' AND staging_target_binding_hash ~ '{_RAW_HASH}' AND "
            f"runner_manifest_hash='{_RUNNER_HASH}' AND "
            f"(provider_run_ref_hash IS NULL OR provider_run_ref_hash ~ '{_RAW_HASH}') AND "
            f"(staging_snapshot_digest IS NULL OR staging_snapshot_digest ~ '{_RAW_HASH}') AND "
            f"(from_artifact_digest IS NULL OR from_artifact_digest ~ '{_RAW_HASH}') AND "
            f"(to_artifact_digest IS NULL OR to_artifact_digest ~ '{_RAW_HASH}') AND "
            f"(artifact_content_hash IS NULL OR artifact_content_hash ~ '{_RAW_HASH}') AND "
            f"(phase_digest IS NULL OR phase_digest ~ '{_RAW_HASH}')",
            name="ck_rollback_verification_runs_hashes",
        ),
        sa.CheckConstraint(
            "char_length(reason_code) BETWEEN 1 AND 128 AND btrim(reason_code)<>'' AND "
            "scope_limitation_code='from_version_connector_observed_not_deployment_fk'",
            name="ck_rollback_verification_runs_codes",
        ),
        sa.CheckConstraint(
            "phase_count BETWEEN 0 AND 5",
            name="ck_rollback_verification_runs_phase_count",
        ),
        sa.CheckConstraint(
            "(attempt_status='succeeded' AND staging_target_snapshot_id IS NOT NULL "
            "AND artifact_provenance='connector_verified_ci_rollback' "
            "AND execution_observation='connector_observed_ci' "
            "AND from_artifact_digest IS NOT NULL AND to_artifact_digest IS NOT NULL "
            "AND from_artifact_digest<>to_artifact_digest AND artifact_content_hash IS NOT NULL "
            "AND provider_run_ref_hash IS NOT NULL "
            "AND phase_digest IS NOT NULL AND phase_count=5 AND artifact_completed_at IS NOT NULL "
            "AND workflow_conclusion IS NOT NULL AND evidence_consistent) OR "
            "(attempt_status IN ('failed','refused') AND artifact_provenance='no_artifact' "
            "AND execution_observation='connector_observation_failed' "
            "AND from_artifact_digest IS NULL AND to_artifact_digest IS NULL "
            "AND provider_run_ref_hash IS NULL AND artifact_content_hash IS NULL "
            "AND phase_digest IS NULL AND phase_count=0 "
            "AND artifact_completed_at IS NULL AND drill_result='incomplete' "
            "AND NOT evidence_consistent AND NOT gate_eligible)",
            name="ck_rollback_verification_runs_result_shape",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            [
                "release_candidates.id",
                "release_candidates.project_id",
                "release_candidates.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["staging_target_snapshot_id", "project_id", "tenant_id"],
            [
                "deployment_target_snapshots.id",
                "deployment_target_snapshots.project_id",
                "deployment_target_snapshots.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_rbvr_id_project_tenant"),
    )
    op.create_index(
        "ix_rvr_tenant_project_created",
        "rollback_verification_runs",
        ["tenant_id", "project_id", "created_at"],
    )


def _create_phases() -> None:
    op.create_table(
        "rollback_verification_phase_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("phase_code", sa.Text(), nullable=False),
        sa.Column("phase_status", sa.Text(), nullable=False),
        sa.Column("result_code", sa.Text(), nullable=False),
        sa.Column("target_binding_hash", sa.Text(), nullable=False),
        sa.Column("expected_version_digest", sa.Text(), nullable=False),
        sa.Column("observed_version_digest", sa.Text(), nullable=True),
        sa.Column("health_ok", sa.Boolean(), nullable=True),
        sa.Column("operation_ok", sa.Boolean(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("ordinal BETWEEN 1 AND 5", name="ck_rvpr_ordinal"),
        sa.CheckConstraint(
            "phase_code IN ('baseline_a_probe','forward_deploy_b','forward_b_probe',"
            "'rollback_to_a','post_rollback_a_probe')",
            name="ck_rvpr_phase_code",
        ),
        sa.CheckConstraint(
            "phase_status IN ('passed','failed','not_run')",
            name="ck_rvpr_phase_status",
        ),
        sa.CheckConstraint(
            "result_code IN ('healthy','unhealthy','operation_complete','operation_failed',"
            "'not_run_after_failure')",
            name="ck_rvpr_result_code",
        ),
        sa.CheckConstraint(
            f"target_binding_hash ~ '{_RAW_HASH}' AND expected_version_digest ~ '{_RAW_HASH}' "
            f"AND (observed_version_digest IS NULL OR observed_version_digest ~ '{_RAW_HASH}')",
            name="ck_rvpr_hashes",
        ),
        sa.CheckConstraint("completed_at>started_at", name="ck_rvpr_timestamps"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            [
                "rollback_verification_runs.id",
                "rollback_verification_runs.project_id",
                "rollback_verification_runs.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_rvpr_run_ordinal"),
        sa.UniqueConstraint("run_id", "phase_code", name="uq_rvpr_run_phase"),
    )


def _create_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.slice52_hash(VARIADIC parts text[]) RETURNS text
        LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog AS $fn$
          SELECT encode(sha256(convert_to(array_to_string(parts, chr(31)), 'UTF8')), 'hex')
        $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.rollback_verification_run_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE c record; p record; s record; expected_target text; expected_snapshot text;
        BEGIN
          SELECT * INTO c FROM public.release_candidates WHERE id=NEW.release_candidate_id;
          SELECT * INTO p FROM public.evidence_packs WHERE id=NEW.evidence_pack_id;
          IF c.id IS NULL OR c.status<>'frozen' OR c.project_id<>NEW.project_id
             OR c.tenant_id<>NEW.tenant_id OR p.id IS NULL OR p.assembly_status<>'complete'
             OR p.release_candidate_id<>c.id OR p.project_id<>NEW.project_id
             OR p.tenant_id<>NEW.tenant_id OR p.repo_binding_state<>'agreed'
             OR p.repo_binding_hash<>NEW.repo_binding_hash OR p.commit_sha<>NEW.commit_sha
             OR p.core_content_hash<>NEW.core_content_hash
             OR p.artifact_scope_digest<>NEW.artifact_scope_digest
             OR p.issue_binding_digest<>NEW.issue_binding_digest
             OR p.source_set_digest<>NEW.source_set_digest
             OR p.traceability_digest<>NEW.traceability_digest THEN
            RAISE EXCEPTION 'rollback exact candidate/core/repo binding mismatch';
          END IF;
          IF NEW.staging_target_snapshot_id IS NOT NULL THEN
            SELECT * INTO s FROM public.deployment_target_snapshots
              WHERE id=NEW.staging_target_snapshot_id;
            IF s.id IS NULL OR s.project_id<>NEW.project_id OR s.tenant_id<>NEW.tenant_id
               OR s.environment<>'staging' OR s.provider<>'generic_https'
               OR s.provenance<>'connector_verified' OR NOT s.target_available
               OR s.observed_at IS NULL THEN
              RAISE EXCEPTION 'rollback staging snapshot is not connector-verified available staging evidence';
            END IF;
            expected_target:=public.slice52_hash(
              NEW.staging_target_contract_version,s.provider,lower(s.target_ref));
            expected_snapshot:=public.slice52_hash(
              s.id::text,to_char(s.observed_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
              s.reachable::text,s.provisioned::text,s.target_available::text,
              COALESCE(s.observed_http_status::text,''),s.provenance);
            IF NEW.staging_target_binding_hash<>expected_target
               OR NEW.staging_snapshot_digest<>expected_snapshot THEN
              RAISE EXCEPTION 'rollback staging snapshot binding digest mismatch';
            END IF;
            IF NEW.attempt_status='succeeded' AND s.observed_at<=NEW.artifact_completed_at THEN
              RAISE EXCEPTION 'rollback staging snapshot must be observed after artifact completion';
            END IF;
          ELSIF NEW.attempt_status='succeeded' THEN
            RAISE EXCEPTION 'rollback succeeded observation requires staging snapshot';
          END IF;
          RETURN NEW;
        END $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER rollback_verification_run_guard BEFORE INSERT ON "
        "public.rollback_verification_runs FOR EACH ROW EXECUTE FUNCTION "
        "public.rollback_verification_run_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.rollback_verification_phase_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE r record; expected_code text; expected_digest text; is_probe boolean;
        BEGIN
          SELECT * INTO r FROM public.rollback_verification_runs WHERE id=NEW.run_id;
          IF r.id IS NULL OR r.attempt_status<>'succeeded' OR r.project_id<>NEW.project_id
             OR r.tenant_id<>NEW.tenant_id THEN
            RAISE EXCEPTION 'rollback phase parent binding mismatch';
          END IF;
          expected_code:=CASE NEW.ordinal
            WHEN 1 THEN 'baseline_a_probe' WHEN 2 THEN 'forward_deploy_b'
            WHEN 3 THEN 'forward_b_probe' WHEN 4 THEN 'rollback_to_a'
            WHEN 5 THEN 'post_rollback_a_probe' END;
          expected_digest:=CASE WHEN NEW.ordinal IN (2,3)
            THEN r.to_artifact_digest ELSE r.from_artifact_digest END;
          is_probe:=NEW.ordinal IN (1,3,5);
          IF NEW.phase_code<>expected_code OR NEW.target_binding_hash<>r.staging_target_binding_hash
             OR NEW.expected_version_digest<>expected_digest THEN
            RAISE EXCEPTION 'rollback phase code/target/version binding mismatch';
          END IF;
          IF NEW.phase_status='passed' AND (
              (is_probe AND (NEW.result_code<>'healthy' OR NEW.health_ok IS DISTINCT FROM true
                 OR NEW.operation_ok IS NOT NULL OR NEW.observed_version_digest<>expected_digest))
              OR (NOT is_probe AND (NEW.result_code<>'operation_complete'
                 OR NEW.operation_ok IS DISTINCT FROM true OR NEW.health_ok IS NOT NULL
                 OR NEW.observed_version_digest IS NOT NULL))) THEN
            RAISE EXCEPTION 'rollback passed phase result mismatch';
          ELSIF NEW.phase_status='failed' AND (
              (is_probe AND (NEW.result_code<>'unhealthy' OR NEW.health_ok IS DISTINCT FROM false
                 OR NEW.operation_ok IS NOT NULL))
              OR (NOT is_probe AND (NEW.result_code<>'operation_failed'
                 OR NEW.operation_ok IS DISTINCT FROM false OR NEW.health_ok IS NOT NULL
                 OR NEW.observed_version_digest IS NOT NULL))) THEN
            RAISE EXCEPTION 'rollback failed phase result mismatch';
          ELSIF NEW.phase_status='not_run' AND (
              NEW.result_code<>'not_run_after_failure' OR NEW.health_ok IS NOT NULL
              OR NEW.operation_ok IS NOT NULL OR NEW.observed_version_digest IS NOT NULL) THEN
            RAISE EXCEPTION 'rollback not-run phase result mismatch';
          END IF;
          RETURN NEW;
        END $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER rollback_verification_phase_guard BEFORE INSERT ON "
        "public.rollback_verification_phase_results FOR EACH ROW EXECUTE FUNCTION "
        "public.rollback_verification_phase_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.verify_rollback_verification_run(run_uuid uuid) RETURNS boolean
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE r record; child_count bigint; failed_count bigint; not_run_count bigint;
        DECLARE computed_phase_digest text; computed_artifact_hash text; expected_result text;
        DECLARE phase_parts text[];
        BEGIN
          SELECT * INTO r FROM public.rollback_verification_runs WHERE id=run_uuid;
          IF r.id IS NULL THEN RETURN true; END IF;
          SELECT count(*),count(*) FILTER (WHERE phase_status='failed'),
                 count(*) FILTER (WHERE phase_status='not_run')
            INTO child_count,failed_count,not_run_count
            FROM public.rollback_verification_phase_results WHERE run_id=r.id;
          IF r.attempt_status<>'succeeded' THEN
            IF child_count<>0 OR r.phase_count<>0 OR r.phase_digest IS NOT NULL
               OR r.drill_result<>'incomplete' OR r.evidence_consistent OR r.gate_eligible THEN
              RAISE EXCEPTION 'failed/refused rollback attempt has result evidence';
            END IF;
            RETURN true;
          END IF;
          IF child_count<>5 OR r.phase_count<>5 THEN
            RAISE EXCEPTION 'rollback phase child set is incomplete';
          END IF;
          IF failed_count>1 OR EXISTS (
            SELECT 1 FROM public.rollback_verification_phase_results x
            WHERE x.run_id=r.id AND (
              (x.phase_status='not_run' AND NOT EXISTS (
                SELECT 1 FROM public.rollback_verification_phase_results prior
                WHERE prior.run_id=r.id AND prior.ordinal<x.ordinal AND prior.phase_status='failed'))
              OR (x.phase_status='passed' AND EXISTS (
                SELECT 1 FROM public.rollback_verification_phase_results prior
                WHERE prior.run_id=r.id AND prior.ordinal<x.ordinal AND prior.phase_status='failed')))) THEN
            RAISE EXCEPTION 'rollback failure/not-run sequence is inconsistent';
          END IF;
          IF EXISTS (
            SELECT 1 FROM public.rollback_verification_phase_results x
            JOIN public.rollback_verification_phase_results prior
              ON prior.run_id=x.run_id AND prior.ordinal=x.ordinal-1
            WHERE x.run_id=r.id AND x.started_at<=prior.completed_at) THEN
            RAISE EXCEPTION 'rollback phase timestamps are not strictly ordered';
          END IF;
          IF r.artifact_completed_at < (
            SELECT max(completed_at) FROM public.rollback_verification_phase_results WHERE run_id=r.id
          ) THEN RAISE EXCEPTION 'rollback artifact completion precedes phase completion'; END IF;
          SELECT array_agg(value ORDER BY ordinal,position) INTO phase_parts FROM (
            SELECT x.ordinal, v.position, v.value
            FROM public.rollback_verification_phase_results x
            CROSS JOIN LATERAL unnest(ARRAY[
              x.ordinal::text,x.phase_code,x.phase_status,x.result_code,x.target_binding_hash,
              x.expected_version_digest,COALESCE(x.observed_version_digest,''),
              COALESCE(x.health_ok::text,''),COALESCE(x.operation_ok::text,''),
              to_char(x.started_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
              to_char(x.completed_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
            ]) WITH ORDINALITY AS v(value,position)
            WHERE x.run_id=r.id
          ) material;
          computed_phase_digest:=public.slice52_hash(
            VARIADIC ARRAY[r.verification_contract_version] || phase_parts);
          computed_artifact_hash:=public.slice52_hash(
            r.drill_contract_version,r.commit_sha,r.staging_target_binding_hash,
            r.from_artifact_digest,r.to_artifact_digest,r.runner_manifest_hash,
            r.workflow_conclusion,
            to_char(r.artifact_completed_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
            computed_phase_digest);
          expected_result:=CASE WHEN r.workflow_conclusion='success'
             AND failed_count=0 AND not_run_count=0 THEN 'passed' ELSE 'failed' END;
          IF r.phase_digest<>computed_phase_digest OR r.artifact_content_hash<>computed_artifact_hash
             OR r.drill_result<>expected_result OR NOT r.evidence_consistent
             OR r.gate_eligible IS DISTINCT FROM (expected_result='passed') THEN
            RAISE EXCEPTION 'rollback generated digest/result/gate eligibility mismatch';
          END IF;
          RETURN true;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.verify_rollback_verification_run_trigger() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE n jsonb:=to_jsonb(NEW); o jsonb:=to_jsonb(OLD); run_uuid uuid;
        BEGIN
          run_uuid:=CASE WHEN TG_TABLE_NAME='rollback_verification_runs'
            THEN COALESCE((n->>'id')::uuid,(o->>'id')::uuid)
            ELSE COALESCE((n->>'run_id')::uuid,(o->>'run_id')::uuid) END;
          PERFORM public.verify_rollback_verification_run(run_uuid); RETURN NULL;
        END $fn$
        """
    )
    for table in ("rollback_verification_runs", "rollback_verification_phase_results"):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_verify AFTER INSERT OR UPDATE OR DELETE "
            f"ON public.{table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION public.verify_rollback_verification_run_trigger()"
        )


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_dts_id_project_tenant",
        "deployment_target_snapshots",
        ["id", "project_id", "tenant_id"],
    )
    _create_runs()
    _create_phases()
    for table in ("rollback_verification_runs", "rollback_verification_phase_results"):
        _tenant_table(table)
    _create_guards()


def downgrade() -> None:
    for table in ("rollback_verification_phase_results", "rollback_verification_runs"):
        count = op.get_bind().execute(sa.text(f"SELECT count(*) FROM public.{table}")).scalar_one()
        if count:
            raise RuntimeError("0051 downgrade refused: Slice-52 rows exist")
    for table in ("rollback_verification_runs", "rollback_verification_phase_results"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_verify ON public.{table}")
    op.execute("DROP FUNCTION IF EXISTS public.verify_rollback_verification_run_trigger()")
    op.execute("DROP FUNCTION IF EXISTS public.verify_rollback_verification_run(uuid)")
    op.execute(
        "DROP TRIGGER IF EXISTS rollback_verification_phase_guard "
        "ON public.rollback_verification_phase_results"
    )
    op.execute("DROP FUNCTION IF EXISTS public.rollback_verification_phase_guard()")
    op.execute(
        "DROP TRIGGER IF EXISTS rollback_verification_run_guard "
        "ON public.rollback_verification_runs"
    )
    op.execute("DROP FUNCTION IF EXISTS public.rollback_verification_run_guard()")
    for table in ("rollback_verification_phase_results", "rollback_verification_runs"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS public.slice52_hash(VARIADIC text[])")
    op.drop_constraint(
        "uq_dts_id_project_tenant",
        "deployment_target_snapshots",
        type_="unique",
    )
