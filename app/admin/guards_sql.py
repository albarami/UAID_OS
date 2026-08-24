"""Guard and append-only trigger bodies for Slice 63."""

from __future__ import annotations

from app.admin.db_checks import (
    RANK_GRANT_G_ROLE_SQL,
    RANK_NEW_ACTOR_ROLE_SQL,
    RANK_NEW_REQUIRED_ROLE_SQL,
)

ADMIN_ACTIONS_GUARD_BODY = f"""DECLARE
    v_n_active int;
    v_max_rank int;
    v_has_role boolean;
    v_actor_rank int;
    v_required_rank int;
BEGIN
    v_actor_rank := {RANK_NEW_ACTOR_ROLE_SQL};
    v_required_rank := {RANK_NEW_REQUIRED_ROLE_SQL};
    SELECT count(*)::int,
           MAX({RANK_GRANT_G_ROLE_SQL}),
           bool_or(g.admin_role = NEW.actor_role)
      INTO v_n_active, v_max_rank, v_has_role
      FROM public.admin_role_grants g
     WHERE g.tenant_id = NEW.tenant_id
       AND g.principal_subject = NEW.actor_principal
       AND g.status = 'active';
    IF NEW.decision = 'allowed' THEN
        IF NOT COALESCE(v_has_role, false) THEN
            RAISE EXCEPTION 'no_active_grant_for_recorded_role';
        END IF;
        IF v_actor_rank IS DISTINCT FROM v_max_rank THEN
            RAISE EXCEPTION 'actor_role_is_not_highest_active_grant';
        END IF;
        IF v_max_rank < v_required_rank THEN
            RAISE EXCEPTION 'highest_active_grant_rank_below_required';
        END IF;
    ELSIF NEW.decision = 'refused_insufficient_role' THEN
        IF NOT COALESCE(v_has_role, false) THEN
            RAISE EXCEPTION 'no_active_grant_for_recorded_role';
        END IF;
        IF v_actor_rank IS DISTINCT FROM v_max_rank THEN
            RAISE EXCEPTION 'actor_role_is_not_highest_active_grant';
        END IF;
        IF NOT (v_max_rank < v_required_rank) THEN
            RAISE EXCEPTION 'sufficient_active_grant_exists';
        END IF;
    ELSIF NEW.decision = 'refused_no_grant' THEN
        IF COALESCE(v_n_active, 0) <> 0 THEN
            RAISE EXCEPTION 'active_grant_exists_for_principal';
        END IF;
    END IF;
    RETURN NEW;
END"""

ADMIN_ROLE_GRANTS_GUARD_BODY = """BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status IS DISTINCT FROM 'active' THEN
            RAISE EXCEPTION 'grant_must_be_born_active';
        END IF;
    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.id IS DISTINCT FROM OLD.id
           OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
           OR NEW.principal_subject IS DISTINCT FROM OLD.principal_subject
           OR NEW.admin_role IS DISTINCT FROM OLD.admin_role
           OR NEW.granted_by IS DISTINCT FROM OLD.granted_by
           OR NEW.granted_by_provenance IS DISTINCT FROM OLD.granted_by_provenance
           OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'grant_identity_immutable';
        END IF;
        IF NOT (OLD.status = 'active' AND NEW.status = 'revoked') THEN
            RAISE EXCEPTION 'grant_status_one_way';
        END IF;
    END IF;
    RETURN NEW;
END"""

ADMIN_POLICY_CHANGES_GUARD_BODY = """DECLARE
    v_decision text;
    v_kind text;
    v_level smallint;
BEGIN
    SELECT a.decision, a.action_kind
      INTO v_decision, v_kind
      FROM public.admin_actions a
     WHERE a.id = NEW.admin_action_id
       AND a.project_id = NEW.project_id
       AND a.tenant_id = NEW.tenant_id;
    IF v_decision IS DISTINCT FROM 'allowed' THEN
        RAISE EXCEPTION 'admin_policy_change_action_not_allowed';
    END IF;
    IF v_kind NOT IN ('set_autonomy_policy','tighten_autonomy_overrides') THEN
        RAISE EXCEPTION 'admin_policy_change_not_policy_kind';
    END IF;
    SELECT p.autonomy_level INTO v_level
      FROM public.autonomy_policies p
     WHERE p.id = NEW.autonomy_policy_id
       AND p.project_id = NEW.project_id
       AND p.tenant_id = NEW.tenant_id;
    IF NEW.new_autonomy_level IS DISTINCT FROM v_level THEN
        RAISE EXCEPTION 'admin_policy_change_level_mismatch';
    END IF;
    IF v_kind = 'tighten_autonomy_overrides'
       AND NEW.previous_autonomy_level IS DISTINCT FROM NEW.new_autonomy_level THEN
        RAISE EXCEPTION 'admin_policy_change_tighten_level_moved';
    END IF;
    RETURN NEW;
END"""

TENANT_ADMIN_EVENTS_GUARD_BODY = """DECLARE
    v_tenant_status text;
    v_tenant_org uuid;
    v_org_status text;
    v_grant_status text;
BEGIN
    SELECT t.status, t.organization_id
      INTO v_tenant_status, v_tenant_org
      FROM public.tenants t WHERE t.id = NEW.tenant_id;
    IF v_tenant_org IS DISTINCT FROM NEW.organization_id THEN
        RAISE EXCEPTION 'event_organization_mismatch';
    END IF;
    SELECT o.status INTO v_org_status
      FROM public.organizations o WHERE o.id = NEW.organization_id;
    IF NEW.event_kind = 'tenant_suspended'
       AND v_tenant_status IS DISTINCT FROM 'suspended' THEN
        RAISE EXCEPTION 'event_tenant_status_mismatch';
    END IF;
    IF NEW.event_kind = 'tenant_reinstated'
       AND v_tenant_status IS DISTINCT FROM 'active' THEN
        RAISE EXCEPTION 'event_tenant_status_mismatch';
    END IF;
    IF NEW.event_kind = 'organization_suspended'
       AND v_org_status IS DISTINCT FROM 'suspended' THEN
        RAISE EXCEPTION 'event_organization_status_mismatch';
    END IF;
    IF NEW.event_kind = 'organization_reinstated'
       AND v_org_status IS DISTINCT FROM 'active' THEN
        RAISE EXCEPTION 'event_organization_status_mismatch';
    END IF;
    IF NEW.event_kind IN ('role_granted','role_revoked')
       AND NEW.admin_role_grant_id IS NOT NULL
       AND NEW.subject_principal IS NOT NULL
       AND NEW.admin_role IS NOT NULL THEN
        SELECT g.status INTO v_grant_status
          FROM public.admin_role_grants g
         WHERE g.id = NEW.admin_role_grant_id
           AND g.tenant_id = NEW.tenant_id;
        IF NEW.event_kind = 'role_granted'
           AND v_grant_status IS DISTINCT FROM 'active' THEN
            RAISE EXCEPTION 'event_grant_status_mismatch';
        END IF;
        IF NEW.event_kind = 'role_revoked'
           AND v_grant_status IS DISTINCT FROM 'revoked' THEN
            RAISE EXCEPTION 'event_grant_status_mismatch';
        END IF;
    END IF;
    RETURN NEW;
END"""


def _fn(name: str, body: str) -> str:
    return (
        f"CREATE OR REPLACE FUNCTION public.{name}() RETURNS trigger "
        "LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$\n"
        f"{body}\n"
        "$fn$"
    )


def block_dml_sql(table: str) -> str:
    """Append-only block function for ``table``."""
    return (
        f"CREATE OR REPLACE FUNCTION public.{table}_block_dml() RETURNS trigger "
        "LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$\n"
        f"BEGIN RAISE EXCEPTION '{table} is append-only'; END\n"
        "$fn$"
    )


ADMIN_ACTIONS_GUARD_SQL = _fn("admin_actions_guard", ADMIN_ACTIONS_GUARD_BODY)
ADMIN_ROLE_GRANTS_GUARD_SQL = _fn("admin_role_grants_guard", ADMIN_ROLE_GRANTS_GUARD_BODY)
ADMIN_POLICY_CHANGES_GUARD_SQL = _fn(
    "admin_policy_changes_guard", ADMIN_POLICY_CHANGES_GUARD_BODY
)
TENANT_ADMIN_EVENTS_GUARD_SQL = _fn(
    "tenant_admin_events_guard", TENANT_ADMIN_EVENTS_GUARD_BODY
)

RESOLVER_FN = "public.resolve_tenant_api_key(text)"

RESOLVER_0062_SQL = """
CREATE FUNCTION public.resolve_tenant_api_key(
    p_key_hash text,
    OUT tenant_id uuid, OUT principal_subject text, OUT actor_type text
) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $fn$
    SELECT k.tenant_id, k.principal_subject, k.actor_type
    FROM public.tenant_api_keys k
    JOIN public.tenants t       ON t.id = k.tenant_id
    JOIN public.organizations o ON o.id = t.organization_id
    WHERE k.key_hash = p_key_hash
      AND k.status = 'active'
      AND t.status = 'active'
      AND o.status = 'active'
    LIMIT 1
$fn$
"""

RESOLVER_0026_SQL = """
CREATE FUNCTION public.resolve_tenant_api_key(
    p_key_hash text,
    OUT tenant_id uuid, OUT principal_subject text, OUT actor_type text
) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $fn$
            SELECT tenant_id, principal_subject, actor_type FROM public.tenant_api_keys
            WHERE key_hash = p_key_hash AND status = 'active'
            LIMIT 1
        $fn$
"""
