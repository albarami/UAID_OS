"""DDL helpers for Slice-61a migration ``0060`` only.

Not imported by the runtime repository path. Keeps ``0060_ecosystem_catalog.py``
under the house 500-line cap.
"""

from __future__ import annotations

from alembic import op

from app.ecosystem.catalog import (
    ADOPTION_LISTING_DELISTED,
    ASSERTION_FORBIDS_RESULTS,
    CHECKER_OUTCOME_MUST_MATCH,
    CHECKER_REQUIRES_FIVE_RESULTS,
    CONNECTOR_CHILDREN_FROZEN,
    CONNECTOR_CHILDREN_REQUIRED,
    DELIST_AT_REQUIRED,
    DELIST_IDENTITY_IMMUTABLE,
    DELIST_ONLY_LISTED_TO_DELISTED,
    DELIST_SAME_STATE_REFUSED,
    LISTING_BLUEPRINT_SELF_REVIEW,
    LISTING_CONNECTOR_CHILDREN_REQUIRED,
    LISTING_MUST_INSERT_LISTED,
    LISTING_VETTING_ASSET_MISMATCH,
    LISTING_VETTING_KIND_MISMATCH,
    LISTING_VETTING_NOT_PASSED,
    LISTING_VETTING_PROVENANCE_MISMATCH,
)

PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
GLOBAL_TABLES: tuple[str, ...] = (
    "catalog_assets",
    "connector_catalog_specs",
    "connector_catalog_tool_scope",
    "catalog_vetting_records",
    "catalog_vetting_check_results",
    "catalog_listings",
)
APPEND_ONLY_TABLES: tuple[str, ...] = (
    "catalog_assets",
    "connector_catalog_specs",
    "connector_catalog_tool_scope",
    "catalog_vetting_records",
    "catalog_vetting_check_results",
    "tenant_catalog_adoptions",
)
ALL_TABLES: tuple[str, ...] = GLOBAL_TABLES + ("tenant_catalog_adoptions",)

CHILDREN_COMPLETE_SQL = """
CREATE FUNCTION public.catalog_connector_children_complete(p_asset uuid)
RETURNS boolean
LANGUAGE sql STABLE SET search_path=pg_catalog AS $fn$
    SELECT (SELECT count(*) FROM public.connector_catalog_specs WHERE asset_id = p_asset) = 1
       AND EXISTS (SELECT 1 FROM public.connector_catalog_tool_scope WHERE asset_id = p_asset)
$fn$
"""

FREEZE_FN_SQL = f"""
CREATE FUNCTION public.catalog_connector_children_freeze() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
BEGIN
    PERFORM 1 FROM public.catalog_assets WHERE id = NEW.asset_id FOR UPDATE;
    IF EXISTS (
        SELECT 1 FROM public.catalog_vetting_records WHERE asset_id = NEW.asset_id
    ) THEN
        RAISE EXCEPTION '{CONNECTOR_CHILDREN_FROZEN}';
    END IF;
    RETURN NEW;
END
$fn$
"""

VETTING_GUARD_SQL = f"""
CREATE FUNCTION public.catalog_vetting_records_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE kind text;
BEGIN
    SELECT asset_kind INTO kind FROM public.catalog_assets WHERE id = NEW.asset_id FOR UPDATE;
    IF kind = 'connector' AND NOT public.catalog_connector_children_complete(NEW.asset_id) THEN
        RAISE EXCEPTION '{CONNECTOR_CHILDREN_REQUIRED}';
    END IF;
    RETURN NEW;
END
$fn$
"""

LISTING_GUARD_SQL = f"""
CREATE FUNCTION public.catalog_listings_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE v_asset uuid; v_kind text; v_outcome text; v_vkind text; v_prov text;
        v_reviewer text; a_kind text; a_reg text;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF OLD.listing_state = NEW.listing_state THEN
            RAISE EXCEPTION '{DELIST_SAME_STATE_REFUSED}';
        END IF;
        IF NOT (OLD.listing_state = 'listed' AND NEW.listing_state = 'delisted') THEN
            RAISE EXCEPTION '{DELIST_ONLY_LISTED_TO_DELISTED}';
        END IF;
        IF NEW.id IS DISTINCT FROM OLD.id
           OR NEW.asset_id IS DISTINCT FROM OLD.asset_id
           OR NEW.vetting_record_id IS DISTINCT FROM OLD.vetting_record_id
           OR NEW.listed_by IS DISTINCT FROM OLD.listed_by
           OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION '{DELIST_IDENTITY_IMMUTABLE}';
        END IF;
        IF NEW.delisted_at IS NULL OR NEW.delisted_reason IS NULL THEN
            RAISE EXCEPTION '{DELIST_AT_REQUIRED}';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.listing_state <> 'listed' OR NEW.delisted_at IS NOT NULL
       OR NEW.delisted_reason IS NOT NULL THEN
        RAISE EXCEPTION '{LISTING_MUST_INSERT_LISTED}';
    END IF;
    SELECT asset_id, outcome, vetting_kind, provenance, reviewer
      INTO v_asset, v_outcome, v_vkind, v_prov, v_reviewer
      FROM public.catalog_vetting_records WHERE id = NEW.vetting_record_id;
    IF v_asset IS DISTINCT FROM NEW.asset_id THEN
        RAISE EXCEPTION '{LISTING_VETTING_ASSET_MISMATCH}';
    END IF;
    IF v_outcome IS DISTINCT FROM 'passed' THEN
        RAISE EXCEPTION '{LISTING_VETTING_NOT_PASSED}';
    END IF;
    SELECT asset_kind, registered_by INTO a_kind, a_reg
      FROM public.catalog_assets WHERE id = NEW.asset_id;
    IF a_kind = 'connector' AND v_vkind IS DISTINCT FROM 'connector_contract_test' THEN
        RAISE EXCEPTION '{LISTING_VETTING_KIND_MISMATCH}';
    END IF;
    IF a_kind = 'agent_blueprint' AND v_vkind IS DISTINCT FROM 'blueprint_security_review' THEN
        RAISE EXCEPTION '{LISTING_VETTING_KIND_MISMATCH}';
    END IF;
    IF a_kind = 'reference_intake'
       AND v_vkind IS DISTINCT FROM 'reference_intake_constraint_attestation' THEN
        RAISE EXCEPTION '{LISTING_VETTING_KIND_MISMATCH}';
    END IF;
    IF a_kind = 'connector' AND v_prov IS DISTINCT FROM 'checker_output_admin_recorded' THEN
        RAISE EXCEPTION '{LISTING_VETTING_PROVENANCE_MISMATCH}';
    END IF;
    IF a_kind IN ('agent_blueprint','reference_intake')
       AND v_prov IS DISTINCT FROM 'reviewer_asserted_admin_recorded' THEN
        RAISE EXCEPTION '{LISTING_VETTING_PROVENANCE_MISMATCH}';
    END IF;
    IF a_kind = 'agent_blueprint' AND v_reviewer IS NOT DISTINCT FROM a_reg THEN
        RAISE EXCEPTION '{LISTING_BLUEPRINT_SELF_REVIEW}';
    END IF;
    IF a_kind = 'connector' AND NOT public.catalog_connector_children_complete(NEW.asset_id) THEN
        RAISE EXCEPTION '{LISTING_CONNECTOR_CHILDREN_REQUIRED}';
    END IF;
    RETURN NEW;
END
$fn$
"""

ADOPTION_GUARD_SQL = f"""
CREATE FUNCTION public.tenant_catalog_adoptions_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE state text;
BEGIN
    SELECT listing_state INTO state FROM public.catalog_listings WHERE id = NEW.listing_id;
    IF state IS DISTINCT FROM 'listed' THEN
        RAISE EXCEPTION '{ADOPTION_LISTING_DELISTED}';
    END IF;
    RETURN NEW;
END
$fn$
"""

SHAPE_FN_SQL = f"""
CREATE FUNCTION public.catalog_vetting_shape_ok(p_id uuid) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE n int; n_pass int; v_prov text; v_out text;
BEGIN
    SELECT provenance, outcome INTO v_prov, v_out
      FROM public.catalog_vetting_records WHERE id = p_id;
    SELECT count(*), count(*) FILTER (WHERE passed) INTO n, n_pass
      FROM public.catalog_vetting_check_results WHERE vetting_record_id = p_id;
    IF v_prov = 'checker_output_admin_recorded' THEN
        IF n IS DISTINCT FROM 5 THEN
            RAISE EXCEPTION '{CHECKER_REQUIRES_FIVE_RESULTS}';
        END IF;
        IF (v_out = 'passed') IS DISTINCT FROM (n_pass = 5) THEN
            RAISE EXCEPTION '{CHECKER_OUTCOME_MUST_MATCH}';
        END IF;
    ELSE
        IF n IS DISTINCT FROM 0 THEN
            RAISE EXCEPTION '{ASSERTION_FORBIDS_RESULTS}';
        END IF;
    END IF;
END
$fn$
"""

PARENT_MATCH_SQL = """
CREATE FUNCTION public.catalog_vetting_records_shape_match() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
BEGIN
    PERFORM public.catalog_vetting_shape_ok(NEW.id);
    RETURN NULL;
END
$fn$
"""

CHILD_MATCH_SQL = """
CREATE FUNCTION public.catalog_vetting_check_results_shape_match() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
BEGIN
    PERFORM public.catalog_vetting_shape_ok(NEW.vetting_record_id);
    RETURN NULL;
END
$fn$
"""


def _block_dml(table: str, ops: str) -> None:
    op.execute(
        f"""CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN RAISE EXCEPTION '{table} is append-only'; END $fn$"""
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_update_delete BEFORE {ops} ON public.{table} "
        f"FOR EACH ROW EXECUTE FUNCTION public.{table}_block_dml()"
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON public.{table} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION public.{table}_block_dml()"
    )


def enable_global_select(table: str) -> None:
    """REVOKE ALL FROM PUBLIC; GRANT SELECT only to uaid_app."""
    op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
    op.execute(f"GRANT SELECT ON public.{table} TO uaid_app")


def enable_tenant_rls(table: str) -> None:
    """ENABLE+FORCE RLS with tenant_isolation and SELECT/INSERT for uaid_app."""
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON public.{table} "
        f"USING ({PREDICATE}) WITH CHECK ({PREDICATE})"
    )
    op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON public.{table} TO uaid_app")


def install_catalog_guards() -> None:
    """Install freeze, listing, shape, append-only, grants, and RLS."""
    op.execute(CHILDREN_COMPLETE_SQL)
    op.execute(FREEZE_FN_SQL)
    op.execute(
        "CREATE TRIGGER connector_spec_freeze_guard BEFORE INSERT "
        "ON public.connector_catalog_specs FOR EACH ROW "
        "EXECUTE FUNCTION public.catalog_connector_children_freeze()"
    )
    op.execute(
        "CREATE TRIGGER connector_scope_freeze_guard BEFORE INSERT "
        "ON public.connector_catalog_tool_scope FOR EACH ROW "
        "EXECUTE FUNCTION public.catalog_connector_children_freeze()"
    )
    op.execute(VETTING_GUARD_SQL)
    op.execute(
        "CREATE TRIGGER catalog_vetting_records_guard BEFORE INSERT "
        "ON public.catalog_vetting_records FOR EACH ROW "
        "EXECUTE FUNCTION public.catalog_vetting_records_guard()"
    )
    op.execute(LISTING_GUARD_SQL)
    op.execute(
        "CREATE TRIGGER catalog_listings_guard BEFORE INSERT OR UPDATE "
        "ON public.catalog_listings FOR EACH ROW "
        "EXECUTE FUNCTION public.catalog_listings_guard()"
    )
    op.execute(ADOPTION_GUARD_SQL)
    op.execute(
        "CREATE TRIGGER tenant_catalog_adoptions_guard BEFORE INSERT "
        "ON public.tenant_catalog_adoptions FOR EACH ROW "
        "EXECUTE FUNCTION public.tenant_catalog_adoptions_guard()"
    )
    op.execute(SHAPE_FN_SQL)
    op.execute(PARENT_MATCH_SQL)
    op.execute(CHILD_MATCH_SQL)
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER catalog_vetting_records_shape_match
            AFTER INSERT ON public.catalog_vetting_records
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.catalog_vetting_records_shape_match()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER catalog_vetting_check_results_shape_match
            AFTER INSERT ON public.catalog_vetting_check_results
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.catalog_vetting_check_results_shape_match()
        """
    )
    for table in APPEND_ONLY_TABLES:
        _block_dml(table, "UPDATE OR DELETE")
    _block_dml("catalog_listings", "DELETE")
    for table in GLOBAL_TABLES:
        enable_global_select(table)
    enable_tenant_rls("tenant_catalog_adoptions")


def drop_catalog_guards() -> None:
    """Reverse ``install_catalog_guards`` after the populated-downgrade check."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.tenant_catalog_adoptions")
    op.execute("ALTER TABLE public.tenant_catalog_adoptions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.tenant_catalog_adoptions DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE SELECT, INSERT ON public.tenant_catalog_adoptions FROM uaid_app")
    for table in GLOBAL_TABLES:
        op.execute(f"REVOKE SELECT ON public.{table} FROM uaid_app")
    for table in ALL_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
    op.execute(
        "DROP TRIGGER IF EXISTS catalog_vetting_check_results_shape_match "
        "ON public.catalog_vetting_check_results"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS catalog_vetting_records_shape_match "
        "ON public.catalog_vetting_records"
    )
    op.execute("DROP FUNCTION IF EXISTS public.catalog_vetting_check_results_shape_match()")
    op.execute("DROP FUNCTION IF EXISTS public.catalog_vetting_records_shape_match()")
    op.execute("DROP FUNCTION IF EXISTS public.catalog_vetting_shape_ok(uuid)")
    op.execute(
        "DROP TRIGGER IF EXISTS tenant_catalog_adoptions_guard ON public.tenant_catalog_adoptions"
    )
    op.execute("DROP FUNCTION IF EXISTS public.tenant_catalog_adoptions_guard()")
    op.execute("DROP TRIGGER IF EXISTS catalog_listings_guard ON public.catalog_listings")
    op.execute("DROP FUNCTION IF EXISTS public.catalog_listings_guard()")
    op.execute(
        "DROP TRIGGER IF EXISTS catalog_vetting_records_guard ON public.catalog_vetting_records"
    )
    op.execute("DROP FUNCTION IF EXISTS public.catalog_vetting_records_guard()")
    op.execute(
        "DROP TRIGGER IF EXISTS connector_scope_freeze_guard ON public.connector_catalog_tool_scope"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS connector_spec_freeze_guard ON public.connector_catalog_specs"
    )
    op.execute("DROP FUNCTION IF EXISTS public.catalog_connector_children_freeze()")
    op.execute("DROP FUNCTION IF EXISTS public.catalog_connector_children_complete(uuid)")


def populated_downgrade_sql() -> str:
    """Refuse a populated 0060→0059 downgrade if any Slice-61a table has rows."""
    exists = " OR ".join(f"EXISTS (SELECT 1 FROM public.{table})" for table in ALL_TABLES)
    return f"""
        DO $fn$
        BEGIN
            IF {exists} THEN
                RAISE EXCEPTION 'cannot downgrade Slice 61a while catalog rows exist';
            END IF;
        END
        $fn$
        """
