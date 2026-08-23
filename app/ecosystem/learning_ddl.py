"""DDL helpers for Slice-62 migration ``0061`` only.

Not imported by the runtime repository path.
"""

from __future__ import annotations

from alembic import op

from app.ecosystem.learning_sql import expected_counts_function_body

PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
GLOBAL_TABLES: tuple[str, ...] = (
    "cross_project_aggregate_runs",
    "cross_project_aggregate_buckets",
)
TENANT_TABLES: tuple[str, ...] = ("cost_optimizer_runs", "cost_optimizer_citations")
ALL_TABLES: tuple[str, ...] = GLOBAL_TABLES + TENANT_TABLES

EXPECTED_COUNTS_FN = f"""
CREATE FUNCTION public.learning_expected_counts(
    p_signal_class text, p_bucket_key text
) RETURNS TABLE (
    n_events int, n_projects int, n_tenants int, metric_sum numeric
) LANGUAGE sql STABLE SET search_path = pg_catalog AS $fn$
{expected_counts_function_body()}
$fn$
"""

COUNTS_MATCH_SQL = """
CREATE FUNCTION public.cross_project_aggregate_buckets_counts_match()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
DECLARE exp_events int; exp_projects int; exp_tenants int; exp_sum numeric;
BEGIN
    SELECT n_events, n_projects, n_tenants, metric_sum
      INTO exp_events, exp_projects, exp_tenants, exp_sum
      FROM public.learning_expected_counts(NEW.signal_class, NEW.bucket_key);
    IF NOT FOUND THEN
        exp_events := 0; exp_projects := 0; exp_tenants := 0; exp_sum := NULL;
    END IF;
    IF NEW.n_events IS DISTINCT FROM exp_events
       OR NEW.n_projects IS DISTINCT FROM exp_projects
       OR NEW.n_tenants IS DISTINCT FROM exp_tenants
       OR NEW.metric_sum IS DISTINCT FROM exp_sum THEN
        RAISE EXCEPTION 'cross_project_aggregate_buckets counts do not match source';
    END IF;
    RETURN NULL;
END
$fn$
"""

CARDINALITY_SQL = """
CREATE FUNCTION public.cross_project_aggregate_cardinality_guard()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
DECLARE parent_id uuid; stored int; child_n int;
BEGIN
    IF TG_TABLE_NAME = 'cross_project_aggregate_runs' THEN
        parent_id := NEW.id; stored := NEW.bucket_count;
    ELSE
        parent_id := NEW.run_id;
        SELECT bucket_count INTO stored
          FROM public.cross_project_aggregate_runs WHERE id = parent_id;
    END IF;
    SELECT count(*) INTO child_n
      FROM public.cross_project_aggregate_buckets WHERE run_id = parent_id;
    IF stored IS DISTINCT FROM 62 OR child_n IS DISTINCT FROM stored THEN
        RAISE EXCEPTION 'cross_project_aggregate cardinality mismatch';
    END IF;
    RETURN NULL;
END
$fn$
"""

PUBLISHED_COUNT_SQL = """
CREATE FUNCTION public.cross_project_aggregate_runs_published_count()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
DECLARE actual int;
BEGIN
    SELECT count(*) FILTER (WHERE published) INTO actual
      FROM public.cross_project_aggregate_buckets WHERE run_id = NEW.id;
    IF NEW.published_bucket_count IS DISTINCT FROM actual THEN
        RAISE EXCEPTION 'cross_project_aggregate published_bucket_count mismatch';
    END IF;
    RETURN NULL;
END
$fn$
"""

OPT_PUBLISHED_SQL = """
CREATE FUNCTION public.cost_optimizer_runs_published_count()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
DECLARE expected int;
BEGIN
    IF NEW.aggregate_run_id IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT published_bucket_count INTO expected
      FROM public.cross_project_aggregate_runs WHERE id = NEW.aggregate_run_id;
    IF NEW.published_bucket_count IS DISTINCT FROM expected THEN
        RAISE EXCEPTION 'cost_optimizer published_bucket_count mismatch';
    END IF;
    RETURN NULL;
END
$fn$
"""

POLICY_FLAGS_SQL = """
CREATE FUNCTION public.cost_optimizer_runs_policy_flags_match()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
DECLARE cheap bool; frontier bool; cached bool;
BEGIN
    IF NEW.flags_source IS DISTINCT FROM 'recorded_cost_policy' THEN
        RETURN NEW;
    END IF;
    SELECT cheap_first_for_low_risk, frontier_for_high_risk,
           use_cached_context_when_possible
      INTO cheap, frontier, cached
      FROM public.cost_forecast_policy_versions
     WHERE id = NEW.policy_version_id
       AND project_id = NEW.project_id
       AND tenant_id = NEW.tenant_id;
    IF NOT FOUND
       OR cheap IS DISTINCT FROM NEW.cheap_first_for_low_risk
       OR frontier IS DISTINCT FROM NEW.frontier_for_high_risk
       OR cached IS DISTINCT FROM NEW.use_cached_context_when_possible THEN
        RAISE EXCEPTION 'cost_optimizer policy flags mismatch';
    END IF;
    RETURN NEW;
END
$fn$
"""

CITATIONS_GUARD_SQL = """
CREATE FUNCTION public.cost_optimizer_citations_guard()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
DECLARE
    parent_id uuid; p_overlay text; p_cite int; p_tool text; p_agg uuid;
    child_n int; miss_n int; n_tool int; n_rework int; n_inf int;
BEGIN
    IF TG_TABLE_NAME = 'cost_optimizer_runs' THEN
        parent_id := NEW.id;
    ELSE
        parent_id := NEW.run_id;
    END IF;
    SELECT overlay_applied, citation_count, tool_name, aggregate_run_id
      INTO p_overlay, p_cite, p_tool, p_agg
      FROM public.cost_optimizer_runs WHERE id = parent_id;
    SELECT count(*) INTO child_n
      FROM public.cost_optimizer_citations WHERE run_id = parent_id;
    IF child_n IS DISTINCT FROM p_cite THEN
        RAISE EXCEPTION 'cost_optimizer citation count mismatch';
    END IF;
    SELECT count(*) INTO miss_n
      FROM public.cost_optimizer_citations c
      LEFT JOIN public.cross_project_published_buckets v
        ON v.id = c.bucket_id AND v.run_id = p_agg
     WHERE c.run_id = parent_id AND v.id IS NULL;
    IF miss_n > 0 THEN
        RAISE EXCEPTION 'cost_optimizer citation not published for run';
    END IF;
    IF p_overlay IN ('none', 'budget_hold') THEN
        IF p_cite IS DISTINCT FROM 0 THEN
            RAISE EXCEPTION 'cost_optimizer overlay citation shape';
        END IF;
    ELSIF p_overlay = 'tool_deny_hold' THEN
        IF p_cite IS DISTINCT FROM 1 OR p_tool IS NULL THEN
            RAISE EXCEPTION 'cost_optimizer overlay citation shape';
        END IF;
        SELECT count(*) INTO n_tool
          FROM public.cost_optimizer_citations c
          JOIN public.cross_project_published_buckets v ON v.id = c.bucket_id
         WHERE c.run_id = parent_id AND v.run_id = p_agg
           AND v.signal_class = 'generic_tool_reliability'
           AND v.bucket_key = p_tool;
        IF n_tool IS DISTINCT FROM 1 THEN
            RAISE EXCEPTION 'cost_optimizer overlay citation shape';
        END IF;
    ELSIF p_overlay = 'rework_intensity_bump' THEN
        IF p_cite IS DISTINCT FROM 2 THEN
            RAISE EXCEPTION 'cost_optimizer overlay citation shape';
        END IF;
        SELECT count(*) FILTER (WHERE v.bucket_key = 'cost:rework'),
               count(*) FILTER (WHERE v.bucket_key = 'cost:model_inference')
          INTO n_rework, n_inf
          FROM public.cost_optimizer_citations c
          JOIN public.cross_project_published_buckets v ON v.id = c.bucket_id
         WHERE c.run_id = parent_id AND v.run_id = p_agg;
        IF n_rework IS DISTINCT FROM 1 OR n_inf IS DISTINCT FROM 1 THEN
            RAISE EXCEPTION 'cost_optimizer overlay citation shape';
        END IF;
    END IF;
    RETURN NULL;
END
$fn$
"""


def _block_dml(table: str) -> None:
    op.execute(
        f"""CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN RAISE EXCEPTION '{table} is append-only'; END $fn$"""
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE "
        f"ON public.{table} FOR EACH ROW "
        f"EXECUTE FUNCTION public.{table}_block_dml()"
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON public.{table} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION public.{table}_block_dml()"
    )


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON public.{table} "
        f"USING ({PREDICATE}) WITH CHECK ({PREDICATE})"
    )
    op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON public.{table} TO uaid_app")


def install_learning_guards() -> None:
    """Install function, view, grants, append-only, RLS, and deferred guards."""
    op.execute(EXPECTED_COUNTS_FN)
    op.execute("REVOKE ALL ON FUNCTION public.learning_expected_counts(text, text) FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION public.learning_expected_counts(text, text) FROM uaid_app")
    op.execute(
        """
        CREATE VIEW public.cross_project_published_buckets
        WITH (security_barrier = true) AS
        SELECT * FROM public.cross_project_aggregate_buckets WHERE published
        """
    )
    op.execute("REVOKE ALL ON public.cross_project_aggregate_runs FROM PUBLIC")
    op.execute("GRANT SELECT ON public.cross_project_aggregate_runs TO uaid_app")
    op.execute("REVOKE ALL ON public.cross_project_aggregate_buckets FROM PUBLIC")
    op.execute("REVOKE ALL ON public.cross_project_aggregate_buckets FROM uaid_app")
    op.execute("REVOKE ALL ON public.cross_project_published_buckets FROM PUBLIC")
    op.execute("GRANT SELECT ON public.cross_project_published_buckets TO uaid_app")
    op.execute(COUNTS_MATCH_SQL)
    op.execute(CARDINALITY_SQL)
    op.execute(PUBLISHED_COUNT_SQL)
    op.execute(OPT_PUBLISHED_SQL)
    op.execute(POLICY_FLAGS_SQL)
    op.execute(CITATIONS_GUARD_SQL)
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER cross_project_aggregate_buckets_counts_match
            AFTER INSERT ON public.cross_project_aggregate_buckets
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION
            public.cross_project_aggregate_buckets_counts_match()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER cross_project_aggregate_runs_cardinality
            AFTER INSERT ON public.cross_project_aggregate_runs
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION
            public.cross_project_aggregate_cardinality_guard()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER cross_project_aggregate_buckets_cardinality
            AFTER INSERT ON public.cross_project_aggregate_buckets
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION
            public.cross_project_aggregate_cardinality_guard()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER cross_project_aggregate_runs_published_count
            AFTER INSERT ON public.cross_project_aggregate_runs
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION
            public.cross_project_aggregate_runs_published_count()
        """
    )
    op.execute(
        """
        CREATE TRIGGER cost_optimizer_runs_policy_flags_match
            BEFORE INSERT ON public.cost_optimizer_runs
            FOR EACH ROW EXECUTE FUNCTION
            public.cost_optimizer_runs_policy_flags_match()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER cost_optimizer_runs_published_count
            AFTER INSERT ON public.cost_optimizer_runs
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION
            public.cost_optimizer_runs_published_count()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER cost_optimizer_runs_citations_guard
            AFTER INSERT ON public.cost_optimizer_runs
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION
            public.cost_optimizer_citations_guard()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER cost_optimizer_citations_row_guard
            AFTER INSERT ON public.cost_optimizer_citations
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION
            public.cost_optimizer_citations_guard()
        """
    )
    for table in ALL_TABLES:
        _block_dml(table)
    for table in TENANT_TABLES:
        _rls(table)


def drop_learning_guards() -> None:
    """Reverse ``install_learning_guards`` after the populated-downgrade check."""
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{table}")
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE SELECT, INSERT ON public.{table} FROM uaid_app")
    op.execute("REVOKE SELECT ON public.cross_project_published_buckets FROM uaid_app")
    op.execute("REVOKE SELECT ON public.cross_project_aggregate_runs FROM uaid_app")
    for table in ALL_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
    op.execute(
        "DROP TRIGGER IF EXISTS cost_optimizer_citations_row_guard "
        "ON public.cost_optimizer_citations"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS cost_optimizer_runs_citations_guard "
        "ON public.cost_optimizer_runs"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS cost_optimizer_runs_published_count "
        "ON public.cost_optimizer_runs"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS cost_optimizer_runs_policy_flags_match "
        "ON public.cost_optimizer_runs"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS cross_project_aggregate_runs_published_count "
        "ON public.cross_project_aggregate_runs"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS cross_project_aggregate_buckets_cardinality "
        "ON public.cross_project_aggregate_buckets"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS cross_project_aggregate_runs_cardinality "
        "ON public.cross_project_aggregate_runs"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS cross_project_aggregate_buckets_counts_match "
        "ON public.cross_project_aggregate_buckets"
    )
    op.execute("DROP FUNCTION IF EXISTS public.cost_optimizer_citations_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.cost_optimizer_runs_policy_flags_match()")
    op.execute("DROP FUNCTION IF EXISTS public.cost_optimizer_runs_published_count()")
    op.execute("DROP FUNCTION IF EXISTS public.cross_project_aggregate_runs_published_count()")
    op.execute("DROP FUNCTION IF EXISTS public.cross_project_aggregate_cardinality_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.cross_project_aggregate_buckets_counts_match()")
    op.execute("DROP VIEW IF EXISTS public.cross_project_published_buckets")
    op.execute("DROP FUNCTION IF EXISTS public.learning_expected_counts(text, text)")


def populated_downgrade_sql() -> str:
    """Refuse a populated 0061→0060 downgrade if any Slice-62 table has rows."""
    exists = " OR ".join(f"EXISTS (SELECT 1 FROM public.{table})" for table in ALL_TABLES)
    return f"""
        DO $fn$
        BEGIN
            IF {exists} THEN
                RAISE EXCEPTION 'cannot downgrade Slice 62 while learning rows exist';
            END IF;
        END
        $fn$
        """
