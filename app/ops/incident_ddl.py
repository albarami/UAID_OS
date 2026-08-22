"""DDL helpers for Slice-57 migration ``0056`` only.

Not imported by the runtime repository path. Keeps ``0056_ops_incidents.py``
under the house 500-line cap.
"""

from __future__ import annotations

from alembic import op

PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
APPEND_TABLES: tuple[str, ...] = (
    "ops_incident_events",
    "ops_incident_tickets",
    "ops_support_handovers",
    "ops_incident_action_evaluations",
    "ops_incident_action_results",
)
_IMMUTABLE = (
    "id",
    "tenant_id",
    "project_id",
    "ruleset_version",
    "category",
    "severity",
    "summary",
    "detail",
    "source_provenance",
    "source_signal_id",
    "idempotency_key",
    "request_digest",
    "created_at",
)


def enable_append_only(table: str) -> None:
    """Block UPDATE/DELETE/TRUNCATE on an append-only incident table."""
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


def enable_rls(table: str, grants: str) -> None:
    """ENABLE+FORCE RLS with tenant_isolation and the named uaid_app grants."""
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON public.{table} "
        f"USING ({PREDICATE}) WITH CHECK ({PREDICATE})"
    )
    op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
    op.execute(f"GRANT {grants} ON public.{table} TO uaid_app")


def install_incident_guards() -> None:
    """Install incident UPDATE guard, delete block, and deferred count-match."""
    immutable = " OR ".join(f"NEW.{col} IS DISTINCT FROM OLD.{col}" for col in _IMMUTABLE)
    op.execute(
        f"""
        CREATE FUNCTION public.ops_incidents_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'open' THEN
                    RAISE EXCEPTION 'ops_incidents must be created with status=open';
                END IF;
            ELSIF TG_OP = 'UPDATE' THEN
                IF {immutable} THEN
                    RAISE EXCEPTION 'ops_incidents identity/content fields are immutable';
                END IF;
                IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
                    RAISE EXCEPTION 'ops_incidents fields change only via a status transition';
                END IF;
                IF NOT (
                    (OLD.status='open' AND NEW.status='investigating')
                    OR (OLD.status='investigating' AND NEW.status='mitigated')
                    OR (OLD.status='mitigated' AND NEW.status IN ('resolved','superseded'))
                ) THEN
                    RAISE EXCEPTION 'ops_incidents illegal transition % -> %', OLD.status, NEW.status;
                END IF;
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER ops_incidents_guard BEFORE INSERT OR UPDATE ON public.ops_incidents "
        "FOR EACH ROW EXECUTE FUNCTION public.ops_incidents_guard()"
    )
    op.execute(
        """CREATE FUNCTION public.ops_incidents_block_delete() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN RAISE EXCEPTION 'ops_incidents is not deletable'; END $fn$"""
    )
    op.execute(
        "CREATE TRIGGER ops_incidents_no_delete BEFORE DELETE ON public.ops_incidents "
        "FOR EACH ROW EXECUTE FUNCTION public.ops_incidents_block_delete()"
    )
    op.execute(
        "CREATE TRIGGER ops_incidents_no_truncate BEFORE TRUNCATE ON public.ops_incidents "
        "FOR EACH STATEMENT EXECUTE FUNCTION public.ops_incidents_block_delete()"
    )
    op.execute(
        """
        CREATE FUNCTION public.ops_incident_action_evaluations_count_match() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE child_count int;
        BEGIN
            SELECT count(*) INTO child_count
              FROM public.ops_incident_action_results WHERE evaluation_id = NEW.id;
            IF NEW.action_count IS DISTINCT FROM 7 OR child_count IS DISTINCT FROM 7 THEN
                RAISE EXCEPTION 'incident evaluation % must have 7 children', NEW.id;
            END IF;
            RETURN NULL;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ops_incident_action_evaluations_count_match
            AFTER INSERT ON public.ops_incident_action_evaluations
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.ops_incident_action_evaluations_count_match()
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.ops_incident_action_results_count_match() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE stored int; child_count int;
        BEGIN
            SELECT action_count INTO stored
              FROM public.ops_incident_action_evaluations WHERE id = NEW.evaluation_id;
            SELECT count(*) INTO child_count
              FROM public.ops_incident_action_results WHERE evaluation_id = NEW.evaluation_id;
            IF stored IS DISTINCT FROM 7 OR child_count IS DISTINCT FROM stored THEN
                RAISE EXCEPTION 'incident evaluation % child counts do not match', NEW.evaluation_id;
            END IF;
            RETURN NULL;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ops_incident_action_results_count_match
            AFTER INSERT ON public.ops_incident_action_results
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.ops_incident_action_results_count_match()
        """
    )
    for table in APPEND_TABLES:
        enable_append_only(table)
    enable_rls("ops_incidents", "SELECT, INSERT, UPDATE")
    for table in APPEND_TABLES:
        enable_rls(table, "SELECT, INSERT")


def drop_incident_guards() -> None:
    """Reverse ``install_incident_guards`` after the populated-downgrade check."""
    for table in APPEND_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{table}")
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE SELECT, INSERT ON public.{table} FROM uaid_app")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.ops_incidents")
    op.execute("ALTER TABLE public.ops_incidents NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.ops_incidents DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE SELECT, INSERT, UPDATE ON public.ops_incidents FROM uaid_app")
    op.execute("DROP TRIGGER IF EXISTS ops_incidents_no_truncate ON public.ops_incidents")
    op.execute("DROP TRIGGER IF EXISTS ops_incidents_no_delete ON public.ops_incidents")
    op.execute("DROP TRIGGER IF EXISTS ops_incidents_guard ON public.ops_incidents")
    op.execute("DROP FUNCTION IF EXISTS public.ops_incidents_block_delete()")
    op.execute("DROP FUNCTION IF EXISTS public.ops_incidents_guard()")
    op.execute(
        "DROP TRIGGER IF EXISTS ops_incident_action_results_count_match "
        "ON public.ops_incident_action_results"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS ops_incident_action_evaluations_count_match "
        "ON public.ops_incident_action_evaluations"
    )
    op.execute("DROP FUNCTION IF EXISTS public.ops_incident_action_results_count_match()")
    op.execute("DROP FUNCTION IF EXISTS public.ops_incident_action_evaluations_count_match()")


def populated_downgrade_sql() -> str:
    """Refuse a populated 0056→0055 downgrade if any Slice-57 table has rows."""
    return """
        DO $fn$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.ops_incidents)
               OR EXISTS (SELECT 1 FROM public.ops_incident_events)
               OR EXISTS (SELECT 1 FROM public.ops_incident_tickets)
               OR EXISTS (SELECT 1 FROM public.ops_support_handovers)
               OR EXISTS (SELECT 1 FROM public.ops_incident_action_evaluations)
               OR EXISTS (SELECT 1 FROM public.ops_incident_action_results) THEN
                RAISE EXCEPTION 'cannot downgrade Slice 57 while incident rows exist';
            END IF;
        END
        $fn$
        """
