"""DDL helpers for Slice-58 migration ``0057`` only.

Not imported by the runtime repository path. Keeps ``0057_self_healing.py``
under the house 500-line cap.
"""

from __future__ import annotations

from alembic import op

PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
TABLES: tuple[str, ...] = (
    "ops_self_healing_runs",
    "ops_hotfix_plans",
    "ops_self_healing_results",
)


def enable_append_only(table: str) -> None:
    """Block UPDATE/DELETE/TRUNCATE on an append-only hotfix-intent table."""
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


def install_hotfix_guards() -> None:
    """Install latch INSERT guard and deferred five-child count-match."""
    op.execute(
        """
        CREATE FUNCTION public.ops_self_healing_runs_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE head text;
        BEGIN
            SELECT e.state_after INTO head
              FROM public.emergency_stop_events e
             WHERE e.tenant_id = NEW.tenant_id AND e.project_id = NEW.project_id
             ORDER BY e.created_at DESC, e.id DESC
             LIMIT 1;
            IF head = 'active' THEN
                RAISE EXCEPTION
                    'ops_self_healing_runs refused while emergency stop is active';
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER ops_self_healing_runs_guard BEFORE INSERT ON public.ops_self_healing_runs "
        "FOR EACH ROW EXECUTE FUNCTION public.ops_self_healing_runs_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.ops_self_healing_runs_count_match() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE child_count int;
        BEGIN
            SELECT count(*) INTO child_count
              FROM public.ops_self_healing_results WHERE run_id = NEW.id;
            IF NEW.action_count IS DISTINCT FROM 5 OR child_count IS DISTINCT FROM 5 THEN
                RAISE EXCEPTION 'hotfix-intent run % must have 5 children', NEW.id;
            END IF;
            RETURN NULL;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ops_self_healing_runs_count_match
            AFTER INSERT ON public.ops_self_healing_runs
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.ops_self_healing_runs_count_match()
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.ops_self_healing_results_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE snap jsonb;
        BEGIN
            SELECT r.decision_snapshot INTO snap
              FROM public.ops_self_healing_runs r WHERE r.id = NEW.run_id;
            IF snap IS NULL
               OR coalesce(snap ->> NEW.matrix_action, '') IS DISTINCT FROM NEW.policy_decision THEN
                RAISE EXCEPTION
                    'hotfix child policy_decision must match run decision_snapshot';
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER ops_self_healing_results_guard "
        "BEFORE INSERT ON public.ops_self_healing_results "
        "FOR EACH ROW EXECUTE FUNCTION public.ops_self_healing_results_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.ops_self_healing_results_plan_order() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM public.ops_self_healing_results r
                 WHERE r.run_id = NEW.run_id AND r.seq = 4 AND r.reason_code = 'plan_written'
            ) AND (
                NOT EXISTS (
                    SELECT 1 FROM public.ops_self_healing_results r
                     WHERE r.run_id = NEW.run_id AND r.seq = 3 AND r.reason_code = 'plan_written'
                ) OR NOT EXISTS (
                    SELECT 1 FROM public.ops_hotfix_plans p
                     WHERE p.run_id = NEW.run_id AND p.plan_kind = 'patch_branch'
                )
            ) THEN
                RAISE EXCEPTION
                    'seq-4 plan_written requires same-run patch_branch plan';
            END IF;
            RETURN NULL;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ops_self_healing_results_plan_order
            AFTER INSERT ON public.ops_self_healing_results
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.ops_self_healing_results_plan_order()
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.ops_self_healing_results_count_match() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE stored int; child_count int;
        BEGIN
            SELECT action_count INTO stored
              FROM public.ops_self_healing_runs WHERE id = NEW.run_id;
            SELECT count(*) INTO child_count
              FROM public.ops_self_healing_results WHERE run_id = NEW.run_id;
            IF stored IS DISTINCT FROM 5 OR child_count IS DISTINCT FROM stored THEN
                RAISE EXCEPTION 'hotfix-intent run % child counts do not match', NEW.run_id;
            END IF;
            RETURN NULL;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ops_self_healing_results_count_match
            AFTER INSERT ON public.ops_self_healing_results
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.ops_self_healing_results_count_match()
        """
    )
    for table in TABLES:
        enable_append_only(table)
        enable_rls(table)


def drop_hotfix_guards() -> None:
    """Reverse ``install_hotfix_guards`` after the populated-downgrade check."""
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{table}")
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE SELECT, INSERT ON public.{table} FROM uaid_app")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
    op.execute(
        "DROP TRIGGER IF EXISTS ops_self_healing_results_plan_order "
        "ON public.ops_self_healing_results"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS ops_self_healing_results_guard ON public.ops_self_healing_results"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS ops_self_healing_results_count_match "
        "ON public.ops_self_healing_results"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS ops_self_healing_runs_count_match ON public.ops_self_healing_runs"
    )
    op.execute("DROP TRIGGER IF EXISTS ops_self_healing_runs_guard ON public.ops_self_healing_runs")
    op.execute("DROP FUNCTION IF EXISTS public.ops_self_healing_results_plan_order()")
    op.execute("DROP FUNCTION IF EXISTS public.ops_self_healing_results_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.ops_self_healing_results_count_match()")
    op.execute("DROP FUNCTION IF EXISTS public.ops_self_healing_runs_count_match()")
    op.execute("DROP FUNCTION IF EXISTS public.ops_self_healing_runs_guard()")


def populated_downgrade_sql() -> str:
    """Refuse a populated 0057→0056 downgrade if any Slice-58 table has rows."""
    return """
        DO $fn$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.ops_self_healing_runs)
               OR EXISTS (SELECT 1 FROM public.ops_hotfix_plans)
               OR EXISTS (SELECT 1 FROM public.ops_self_healing_results) THEN
                RAISE EXCEPTION 'cannot downgrade Slice 58 while hotfix-intent rows exist';
            END IF;
        END
        $fn$
        """
