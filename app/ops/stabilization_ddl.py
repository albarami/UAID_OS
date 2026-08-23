"""DDL helpers for Slice-59 migration ``0058`` only.

Not imported by the runtime repository path. Keeps ``0058_stabilization.py``
under the house 500-line cap.
"""

from __future__ import annotations

from alembic import op

PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
TABLES: tuple[str, ...] = (
    "ops_stabilization_windows",
    "ops_stabilization_criterion_results",
    "ops_improvement_results",
    "ops_stabilization_closure_attempts",
)

DIGEST_SQL = """
CREATE FUNCTION public.jsonb_canonical_text(j jsonb) RETURNS text
LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog AS $fn$
  SELECT CASE jsonb_typeof(j)
    WHEN 'object' THEN '{' || COALESCE((
      SELECT string_agg(to_json(key)::text || ':' || public.jsonb_canonical_text(value), ','
             ORDER BY key)
      FROM jsonb_each(j) AS t(key, value)
    ), '') || '}'
    WHEN 'array' THEN '[' || COALESCE((
      SELECT string_agg(public.jsonb_canonical_text(value), ',' ORDER BY ordinality)
      FROM jsonb_array_elements(j) WITH ORDINALITY AS t(value, ordinality)
    ), '') || ']'
    ELSE j::text
  END
$fn$
"""

POLICY_DIGEST_SQL = """
CREATE FUNCTION public.stabilization_policy_digest(j jsonb) RETURNS text
LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog AS $fn$
  SELECT 'sha256:' || encode(sha256(convert_to(public.jsonb_canonical_text(j), 'UTF8')), 'hex')
$fn$
"""

WINDOW_GUARD_SQL = r"""
CREATE FUNCTION public.ops_stabilization_windows_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE declared text; prior record;
BEGIN
    IF NEW.status IS DISTINCT FROM 'open' THEN
        RAISE EXCEPTION 'ops_stabilization_windows status must be open';
    END IF;
    IF NEW.criterion_count IS DISTINCT FROM 8 OR NEW.improvement_count IS DISTINCT FROM 8 THEN
        RAISE EXCEPTION 'ops_stabilization_windows child counts must be 8';
    END IF;
    IF NEW.extension_required IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION 'ops_stabilization_windows extension_required must be true';
    END IF;
    IF NEW.policy_digest IS DISTINCT FROM public.stabilization_policy_digest(NEW.policy_snapshot) THEN
        RAISE EXCEPTION 'ops_stabilization_windows policy_digest mismatch';
    END IF;
    IF NEW.as_of IS DISTINCT FROM transaction_timestamp() THEN
        RAISE EXCEPTION 'ops_stabilization_windows as_of must equal transaction_timestamp()';
    END IF;
    IF NEW.monitoring_max_age_hours IS NULL OR NEW.deployment_max_age_hours IS NULL
       OR NEW.monitoring_max_age_hours NOT BETWEEN 1 AND 168
       OR NEW.deployment_max_age_hours NOT BETWEEN 1 AND 168 THEN
        RAISE EXCEPTION 'ops_stabilization_windows age hours out of range';
    END IF;
    SELECT c.data->'monitoring'->>'status_url' INTO declared
      FROM public.intake_categories c
     WHERE c.id = NEW.category_id
       AND c.tenant_id = NEW.tenant_id
       AND c.project_id = NEW.project_id
       AND c.category = 'operations_observability_support'
       AND c.status = 'declared'
       AND c.data->'monitoring'->>'provider' = 'generic_monitoring_api';
    IF NEW.monitoring_target_ref IS NOT NULL
       AND (declared IS NULL OR NEW.monitoring_target_ref IS DISTINCT FROM declared) THEN
        RAISE EXCEPTION 'ops_stabilization_windows monitoring_target_ref is not the declared target';
    END IF;
    IF NEW.extends_window_id IS NOT NULL THEN
        SELECT * INTO prior FROM public.ops_stabilization_windows p
         WHERE p.id = NEW.extends_window_id
           AND p.tenant_id = NEW.tenant_id
           AND p.project_id = NEW.project_id;
        IF prior IS NULL OR prior.extension_required IS DISTINCT FROM TRUE
           OR prior.id IS NOT DISTINCT FROM NEW.id THEN
            RAISE EXCEPTION 'ops_stabilization_windows extends_window_id is not a prior required window';
        END IF;
    END IF;
    RETURN NEW;
END
$fn$
"""

CRITERION_GUARD_SQL = r"""
CREATE FUNCTION public.ops_stabilization_criterion_results_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE parent record; snap record; ho record;
BEGIN
    SELECT * INTO parent FROM public.ops_stabilization_windows WHERE id = NEW.window_id;
    IF parent IS NULL THEN
        RAISE EXCEPTION 'stabilization criterion parent window is missing';
    END IF;
    IF NEW.seq = 3 THEN
        IF NEW.status IS NOT DISTINCT FROM 'passed' THEN
            RAISE EXCEPTION 'seq 3 cannot be passed';
        END IF;
        IF NEW.reason IN ('no_monitoring_declaration','monitoring_declared_but_no_evidence') THEN
            IF NEW.monitoring_snapshot_id IS NOT NULL THEN
                RAISE EXCEPTION 'seq 3 missing-evidence rows must not cite a snapshot';
            END IF;
        ELSE
            IF NEW.monitoring_snapshot_id IS NULL THEN
                RAISE EXCEPTION 'seq 3 observed rows must cite a snapshot';
            END IF;
            IF parent.monitoring_target_ref IS NULL THEN
                RAISE EXCEPTION 'seq 3 snapshot requires a labelled monitoring_target_ref';
            END IF;
            SELECT * INTO snap FROM public.monitoring_status_snapshots
             WHERE id = NEW.monitoring_snapshot_id
               AND tenant_id = NEW.tenant_id AND project_id = NEW.project_id;
            IF snap IS NULL
               OR snap.provider IS DISTINCT FROM 'generic_monitoring_api'
               OR snap.target_ref IS DISTINCT FROM parent.monitoring_target_ref THEN
                RAISE EXCEPTION 'seq 3 snapshot is not the declared monitoring target';
            END IF;
        END IF;
    ELSIF NEW.seq = 4 THEN
        IF NEW.status IS NOT DISTINCT FROM 'passed' THEN
            RAISE EXCEPTION 'seq 4 cannot be passed';
        END IF;
        IF NEW.reason IS NOT DISTINCT FROM 'no_rollback_run' THEN
            IF NEW.rollback_verification_run_id IS NOT NULL THEN
                RAISE EXCEPTION 'seq 4 no_rollback_run must not cite a run';
            END IF;
        ELSE
            IF NEW.rollback_verification_run_id IS NULL THEN
                RAISE EXCEPTION 'seq 4 observed rows must cite a run';
            END IF;
        END IF;
    ELSIF NEW.seq = 5 AND NEW.status IS NOT DISTINCT FROM 'passed' THEN
        IF NEW.handover_id IS NULL THEN
            RAISE EXCEPTION 'seq 5 passed requires a handover row';
        END IF;
        SELECT * INTO ho FROM public.ops_support_handovers
         WHERE id = NEW.handover_id AND tenant_id = NEW.tenant_id AND project_id = NEW.project_id;
        IF ho IS NULL OR ho.status IS DISTINCT FROM 'recorded_complete' THEN
            RAISE EXCEPTION 'seq 5 passed requires recorded_complete handover';
        END IF;
        IF EXISTS (
            SELECT 1 FROM public.ops_support_handovers h
             WHERE h.tenant_id = NEW.tenant_id AND h.project_id = NEW.project_id
               AND (h.created_at, h.id) > (ho.created_at, ho.id)
        ) THEN
            RAISE EXCEPTION 'seq 5 passed requires the latest handover row';
        END IF;
    ELSIF NEW.seq IN (1,2,6,7,8) AND NEW.status IS NOT DISTINCT FROM 'passed' THEN
        RAISE EXCEPTION 'seq % cannot be passed', NEW.seq;
    END IF;
    RETURN NEW;
END
$fn$
"""

IMPROVEMENT_GUARD_SQL = r"""
CREATE FUNCTION public.ops_improvement_results_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
BEGIN
    IF NEW.seq IN (1,3,4,8) AND NEW.status IS DISTINCT FROM 'not_observed' THEN
        RAISE EXCEPTION 'improvement seq % is locked to not_observed', NEW.seq;
    END IF;
    IF NEW.seq = 6 AND NEW.status IS NOT DISTINCT FROM 'observed'
       AND NEW.findings_report_id IS NULL THEN
        RAISE EXCEPTION 'improvement seq 6 observed requires findings_report_id';
    END IF;
    IF NEW.seq = 7 AND NEW.status IS NOT DISTINCT FROM 'observed'
       AND NEW.cost_forecast_run_id IS NULL THEN
        RAISE EXCEPTION 'improvement seq 7 observed requires cost_forecast_run_id';
    END IF;
    RETURN NEW;
END
$fn$
"""

COUNT_MATCH_SQL = r"""
CREATE FUNCTION public.ops_stabilization_windows_count_match() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE c_count int; i_count int; passed int; failed int; missing int; uneval int;
        c_seqs int; i_seqs int;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE status='passed'),
           count(*) FILTER (WHERE status='failed'),
           count(*) FILTER (WHERE status='not_observed'),
           count(*) FILTER (WHERE status='not_evaluable'),
           count(DISTINCT seq) FILTER (WHERE seq BETWEEN 1 AND 8)
      INTO c_count, passed, failed, missing, uneval, c_seqs
      FROM public.ops_stabilization_criterion_results WHERE window_id = NEW.id;
    SELECT count(*), count(DISTINCT seq) FILTER (WHERE seq BETWEEN 1 AND 8)
      INTO i_count, i_seqs
      FROM public.ops_improvement_results WHERE window_id = NEW.id;
    IF NEW.criterion_count IS DISTINCT FROM 8 OR c_count IS DISTINCT FROM 8
       OR c_seqs IS DISTINCT FROM 8
       OR NEW.improvement_count IS DISTINCT FROM 8 OR i_count IS DISTINCT FROM 8
       OR i_seqs IS DISTINCT FROM 8
       OR NEW.passed_count IS DISTINCT FROM passed
       OR NEW.failed_count IS DISTINCT FROM failed
       OR NEW.not_observed_count IS DISTINCT FROM missing
       OR NEW.not_evaluable_count IS DISTINCT FROM uneval
       OR NEW.extension_required IS DISTINCT FROM (passed < 8) THEN
        RAISE EXCEPTION 'stabilization window % child tallies do not match', NEW.id;
    END IF;
    RETURN NULL;
END
$fn$
"""

CHILD_COUNT_MATCH_SQL = r"""
CREATE FUNCTION public.ops_stabilization_children_count_match() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE stored record; c_count int; i_count int; passed int; failed int;
        missing int; uneval int; c_seqs int; i_seqs int;
BEGIN
    SELECT * INTO stored FROM public.ops_stabilization_windows WHERE id = NEW.window_id;
    SELECT count(*),
           count(*) FILTER (WHERE status='passed'),
           count(*) FILTER (WHERE status='failed'),
           count(*) FILTER (WHERE status='not_observed'),
           count(*) FILTER (WHERE status='not_evaluable'),
           count(DISTINCT seq) FILTER (WHERE seq BETWEEN 1 AND 8)
      INTO c_count, passed, failed, missing, uneval, c_seqs
      FROM public.ops_stabilization_criterion_results WHERE window_id = NEW.window_id;
    SELECT count(*), count(DISTINCT seq) FILTER (WHERE seq BETWEEN 1 AND 8)
      INTO i_count, i_seqs
      FROM public.ops_improvement_results WHERE window_id = NEW.window_id;
    IF stored.criterion_count IS DISTINCT FROM 8 OR c_count IS DISTINCT FROM 8
       OR c_seqs IS DISTINCT FROM 8
       OR stored.improvement_count IS DISTINCT FROM 8 OR i_count IS DISTINCT FROM 8
       OR i_seqs IS DISTINCT FROM 8
       OR stored.passed_count IS DISTINCT FROM passed
       OR stored.failed_count IS DISTINCT FROM failed
       OR stored.not_observed_count IS DISTINCT FROM missing
       OR stored.not_evaluable_count IS DISTINCT FROM uneval
       OR stored.extension_required IS DISTINCT FROM (passed < 8) THEN
        RAISE EXCEPTION 'stabilization window % child tallies do not match', NEW.window_id;
    END IF;
    RETURN NULL;
END
$fn$
"""


def enable_append_only(table: str) -> None:
    """Block UPDATE/DELETE/TRUNCATE on an append-only stabilization table."""
    op.execute(
        f"""CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN RAISE EXCEPTION '{table} is append-only'; END $fn$"""
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON public.{table} "
        f"FOR EACH ROW EXECUTE FUNCTION public.{table}_block_dml()"
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON public.{table} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION public.{table}_block_dml()"
    )


def enable_rls(table: str) -> None:
    """ENABLE+FORCE RLS with tenant_isolation and SELECT/INSERT for uaid_app."""
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON public.{table} "
        f"USING ({PREDICATE}) WITH CHECK ({PREDICATE})"
    )
    op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON public.{table} TO uaid_app")


def install_stabilization_guards() -> None:
    """Install digest helpers, INSERT guards, and deferred 8+8 tally triggers."""
    op.execute(DIGEST_SQL)
    op.execute(POLICY_DIGEST_SQL)
    op.execute("REVOKE ALL ON FUNCTION public.jsonb_canonical_text(jsonb) FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION public.stabilization_policy_digest(jsonb) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.jsonb_canonical_text(jsonb) TO uaid_app")
    op.execute("GRANT EXECUTE ON FUNCTION public.stabilization_policy_digest(jsonb) TO uaid_app")
    op.execute(WINDOW_GUARD_SQL)
    op.execute(
        "CREATE TRIGGER ops_stabilization_windows_guard "
        "BEFORE INSERT ON public.ops_stabilization_windows "
        "FOR EACH ROW EXECUTE FUNCTION public.ops_stabilization_windows_guard()"
    )
    op.execute(CRITERION_GUARD_SQL)
    op.execute(
        "CREATE TRIGGER ops_stabilization_criterion_results_guard "
        "BEFORE INSERT ON public.ops_stabilization_criterion_results "
        "FOR EACH ROW EXECUTE FUNCTION public.ops_stabilization_criterion_results_guard()"
    )
    op.execute(IMPROVEMENT_GUARD_SQL)
    op.execute(
        "CREATE TRIGGER ops_improvement_results_guard "
        "BEFORE INSERT ON public.ops_improvement_results "
        "FOR EACH ROW EXECUTE FUNCTION public.ops_improvement_results_guard()"
    )
    op.execute(COUNT_MATCH_SQL)
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ops_stabilization_windows_count_match
            AFTER INSERT ON public.ops_stabilization_windows
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.ops_stabilization_windows_count_match()
        """
    )
    op.execute(CHILD_COUNT_MATCH_SQL)
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ops_stabilization_criterion_results_count_match
            AFTER INSERT ON public.ops_stabilization_criterion_results
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.ops_stabilization_children_count_match()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ops_improvement_results_count_match
            AFTER INSERT ON public.ops_improvement_results
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.ops_stabilization_children_count_match()
        """
    )
    for table in TABLES:
        enable_append_only(table)
        enable_rls(table)


def drop_stabilization_guards() -> None:
    """Reverse ``install_stabilization_guards`` after the populated-downgrade check."""
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{table}")
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE SELECT, INSERT ON public.{table} FROM uaid_app")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
    op.execute(
        "DROP TRIGGER IF EXISTS ops_improvement_results_count_match "
        "ON public.ops_improvement_results"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS ops_stabilization_criterion_results_count_match "
        "ON public.ops_stabilization_criterion_results"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS ops_stabilization_windows_count_match "
        "ON public.ops_stabilization_windows"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS ops_improvement_results_guard ON public.ops_improvement_results"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS ops_stabilization_criterion_results_guard "
        "ON public.ops_stabilization_criterion_results"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS ops_stabilization_windows_guard ON public.ops_stabilization_windows"
    )
    op.execute("DROP FUNCTION IF EXISTS public.ops_stabilization_children_count_match()")
    op.execute("DROP FUNCTION IF EXISTS public.ops_stabilization_windows_count_match()")
    op.execute("DROP FUNCTION IF EXISTS public.ops_improvement_results_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.ops_stabilization_criterion_results_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.ops_stabilization_windows_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.stabilization_policy_digest(jsonb)")
    op.execute("DROP FUNCTION IF EXISTS public.jsonb_canonical_text(jsonb)")


def populated_downgrade_sql() -> str:
    """Refuse a populated 0058→0057 downgrade if any Slice-59 table has rows."""
    return """
        DO $fn$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.ops_stabilization_windows)
               OR EXISTS (SELECT 1 FROM public.ops_stabilization_criterion_results)
               OR EXISTS (SELECT 1 FROM public.ops_improvement_results)
               OR EXISTS (SELECT 1 FROM public.ops_stabilization_closure_attempts) THEN
                RAISE EXCEPTION 'cannot downgrade Slice 59 while stabilization rows exist';
            END IF;
        END
        $fn$
        """
