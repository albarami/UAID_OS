"""Writer and monotonic-helper SQL for Slice 63 (§OD-11/§OD-12).

The CREATE text is assembled from named clauses so probe pairs can remove
exactly one clause while leaving the rest byte-identical.
"""

from __future__ import annotations

WRITER_SIG = (
    "public.admin_write_autonomy_policy("
    "p_admin_action_id uuid, p_project_id uuid, "
    "p_autonomy_level smallint, p_overrides jsonb, "
    "OUT o_autonomy_policy_id uuid, OUT o_admin_policy_change_id uuid)"
)
MONOTONIC_SIG = "public.admin_overrides_is_monotonic(jsonb, jsonb)"

GUC_CLAUSE = """    v_tenant := NULLIF(current_setting('app.current_tenant', true), '')::uuid;
    IF v_tenant IS NULL THEN
        RAISE EXCEPTION 'tenant_guc_unset';
    END IF;"""

GUC_FALLBACK = """    v_tenant := NULLIF(current_setting('app.current_tenant', true), '')::uuid;
    IF v_tenant IS NULL THEN
        SELECT a.tenant_id INTO v_tenant
          FROM public.admin_actions a
         WHERE a.id = p_admin_action_id AND a.project_id = p_project_id;
    END IF;"""

ALLOWED_CLAUSE = """    IF v_decision IS DISTINCT FROM 'allowed' THEN
        RAISE EXCEPTION 'admin_action_not_allowed';
    END IF;"""

KIND_CLAUSE = """    IF v_kind NOT IN ('set_autonomy_policy','tighten_autonomy_overrides') THEN
        RAISE EXCEPTION 'admin_action_not_policy_kind';
    END IF;"""

NO_EXISTING_CLAUSE = """        IF NOT FOUND THEN
            RAISE EXCEPTION 'no_existing_policy';
        END IF;"""

TIGHTEN_LEVEL_CLAUSE = """        IF p_autonomy_level IS DISTINCT FROM v_previous_level THEN
            RAISE EXCEPTION 'tighten_may_not_change_level';
        END IF;"""

MONOTONIC_CLAUSE = """        IF NOT public.admin_overrides_is_monotonic(v_stored_overrides, p_overrides) THEN
            RAISE EXCEPTION 'tighten_would_relax_overrides';
        END IF;"""

_LOAD_ACTION = """    SELECT a.decision, a.action_kind
      INTO v_decision, v_kind
      FROM public.admin_actions a
     WHERE a.id = p_admin_action_id
       AND a.tenant_id = v_tenant
       AND a.project_id = p_project_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no_such_admin_action';
    END IF;"""

_LOAD_POLICY = """    SELECT p.id, p.autonomy_level, p.overrides
      INTO o_autonomy_policy_id, v_previous_level, v_stored_overrides
      FROM public.autonomy_policies p
     WHERE p.tenant_id = v_tenant AND p.project_id = p_project_id
     FOR UPDATE;"""

_RECORD_PROBE = """    v_found := FOUND;
    v_created := FALSE;"""

_SPEND = """    SELECT count(*)::smallint INTO v_override_key_count
      FROM jsonb_object_keys(COALESCE(p_overrides, '{}'::jsonb));
    BEGIN
        INSERT INTO public.admin_policy_changes (
            tenant_id, project_id, admin_action_id, autonomy_policy_id,
            previous_autonomy_level, new_autonomy_level, override_key_count
        ) VALUES (
            v_tenant, p_project_id, p_admin_action_id, o_autonomy_policy_id,
            v_previous_level, p_autonomy_level, v_override_key_count
        )
        RETURNING id INTO o_admin_policy_change_id;
    EXCEPTION WHEN unique_violation THEN
        RAISE EXCEPTION 'admin_action_already_spent';
    END;"""

# Approved-v4 body kept only so the two-writer mutation can reinstall it.
_RACY_UPSERT_AND_SPEND = (
    """    INSERT INTO public.autonomy_policies (
        tenant_id, project_id, autonomy_level, overrides, updated_at
    ) VALUES (
        v_tenant, p_project_id, p_autonomy_level,
        COALESCE(p_overrides, '{}'::jsonb), now()
    )
    ON CONFLICT (tenant_id, project_id) DO UPDATE
        SET autonomy_level = EXCLUDED.autonomy_level,
            overrides = EXCLUDED.overrides,
            updated_at = now()
    RETURNING id INTO o_autonomy_policy_id;
"""
    + _SPEND
)

_SERIALIZE_THEN_UPDATE = """    IF NOT v_found THEN
        INSERT INTO public.autonomy_policies (
            tenant_id, project_id, autonomy_level, overrides, updated_at
        ) VALUES (
            v_tenant, p_project_id, p_autonomy_level,
            COALESCE(p_overrides, '{}'::jsonb), now()
        )
        ON CONFLICT (tenant_id, project_id) DO NOTHING
        RETURNING id INTO o_autonomy_policy_id;
        v_created := FOUND;
        SELECT p.id, p.autonomy_level, p.overrides
          INTO o_autonomy_policy_id, v_previous_level, v_stored_overrides
          FROM public.autonomy_policies p
         WHERE p.tenant_id = v_tenant AND p.project_id = p_project_id
         FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'policy_write_row_unavailable';
        END IF;
        IF v_created THEN
            v_previous_level := NULL;
        END IF;
    END IF;
    UPDATE public.autonomy_policies
       SET autonomy_level = p_autonomy_level,
           overrides = COALESCE(p_overrides, '{}'::jsonb),
           updated_at = now()
     WHERE tenant_id = v_tenant AND project_id = p_project_id
     RETURNING id INTO o_autonomy_policy_id;"""

_SERIALIZE_AND_SPEND = _SERIALIZE_THEN_UPDATE + "\n" + _SPEND


def writer_body(
    *,
    omit_allowed: bool = False,
    omit_kind: bool = False,
    omit_guc: bool = False,
    guc_fallback: bool = False,
    omit_no_existing: bool = False,
    omit_tighten_level: bool = False,
    omit_monotonic: bool = False,
    racy_first_write: bool = False,
) -> str:
    """Return the plpgsql body with named clauses optionally removed."""
    if guc_fallback:
        guc = GUC_FALLBACK
    elif omit_guc:
        guc = "    v_tenant := NULLIF(current_setting('app.current_tenant', true), '')::uuid;"
    else:
        guc = GUC_CLAUSE
    allowed = "" if omit_allowed else ALLOWED_CLAUSE
    kind = "" if omit_kind else KIND_CLAUSE
    existence = "" if omit_no_existing else NO_EXISTING_CLAUSE
    level = "" if omit_tighten_level else TIGHTEN_LEVEL_CLAUSE
    mono = "" if omit_monotonic else MONOTONIC_CLAUSE
    tighten = "\n".join(part for part in (existence, level, mono) if part)
    tighten_block = (
        f"    IF v_kind = 'tighten_autonomy_overrides' THEN\n{tighten}\n    END IF;"
        if tighten
        else ""
    )
    found_vars = "" if racy_first_write else "    v_found boolean;\n    v_created boolean;\n"
    parts = [
        "DECLARE\n"
        "    v_tenant uuid;\n"
        "    v_decision text;\n"
        "    v_kind text;\n"
        f"{found_vars}"
        "    v_previous_level smallint;\n"
        "    v_stored_overrides jsonb;\n"
        "    v_override_key_count smallint;\n"
        "BEGIN",
        guc,
        _LOAD_ACTION,
        allowed,
        kind,
        _LOAD_POLICY,
        "" if racy_first_write else _RECORD_PROBE,
        tighten_block,
        _RACY_UPSERT_AND_SPEND if racy_first_write else _SERIALIZE_AND_SPEND,
        "END",
    ]
    return "\n".join(part for part in parts if part)


WRITER_BODY = writer_body()

MONOTONIC_BODY = """SELECT NOT EXISTS (
  SELECT 1
  FROM jsonb_each(COALESCE(p_old, '{}'::jsonb)) AS o(action, ov)
  WHERE
       NOT (COALESCE(p_new, '{}'::jsonb) ? o.action)
    OR (ov ? 'allow'
        AND (p_new -> o.action -> 'allow') IS DISTINCT FROM to_jsonb(false))
    OR (ov ? 'requires_approval'
        AND (p_new -> o.action -> 'requires_approval') IS DISTINCT FROM to_jsonb(true))
    OR (ov ? 'min_level'
        AND (   NOT (p_new -> o.action ? 'min_level')
             OR (p_new -> o.action ->> 'min_level')::int < (ov ->> 'min_level')::int))
)"""


def writer_create_sql(**kwargs: bool) -> str:
    """CREATE FUNCTION wrapping ``writer_body``."""
    body = writer_body(**kwargs)
    return (
        "CREATE OR REPLACE FUNCTION "
        f"{WRITER_SIG} LANGUAGE plpgsql SECURITY DEFINER "
        "SET search_path = pg_catalog AS $fn$\n"
        f"{body}\n"
        "$fn$"
    )


def monotonic_create_sql() -> str:
    """CREATE FUNCTION for the IMMUTABLE monotonic helper."""
    return (
        "CREATE OR REPLACE FUNCTION public.admin_overrides_is_monotonic("
        "p_old jsonb, p_new jsonb) RETURNS boolean "
        "LANGUAGE sql IMMUTABLE SET search_path = pg_catalog AS $fn$\n"
        f"{MONOTONIC_BODY}\n"
        "$fn$"
    )


WRITER_CREATE_SQL = writer_create_sql()
MONOTONIC_CREATE_SQL = monotonic_create_sql()
