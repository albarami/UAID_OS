"""Named CHECK strings and generated rank CASE snippets (§OD-6).

Consumed by the ORM, ``guards_sql.py``, and migration ``0062``. Editing
``ROLE_RANKS`` without re-running the migration fails A-check-drift.
"""

from __future__ import annotations

from app.admin.rbac import (
    ACTION_REQUIRED_ROLE,
    ADMIN_ACTION_KINDS,
    ADMIN_ROLES,
    DECISIONS,
    ROLE_RANKS,
    RULESET_VERSION,
)

_WS = r"E' \t\n\r\x0b\x0c'"


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def _nonblank(column: str, max_len: int) -> str:
    return (
        f"char_length({column}) BETWEEN 1 AND {max_len} "
        f"AND btrim({column}, {_WS}) <> ''"
    )


def rank_case(column: str) -> str:
    """Inline SQL CASE mapping ``column`` onto ``ROLE_RANKS``."""
    branches = " ".join(
        f"WHEN '{role}' THEN {rank}" for role, rank in ROLE_RANKS.items()
    )
    return f"CASE {column} {branches} END"


def required_role_case(column: str = "action_kind") -> str:
    """Inline SQL CASE mapping ``action_kind`` onto ``ACTION_REQUIRED_ROLE``."""
    branches = " ".join(
        f"WHEN '{kind}' THEN '{role}'" for kind, role in ACTION_REQUIRED_ROLE.items()
    )
    return f"CASE {column} {branches} END"


RANK_ACTOR_ROLE_SQL = rank_case("actor_role")
RANK_REQUIRED_ROLE_SQL = rank_case("required_role")
RANK_GRANT_ROLE_SQL = rank_case("admin_role")
RANK_NEW_ACTOR_ROLE_SQL = rank_case("NEW.actor_role")
RANK_NEW_REQUIRED_ROLE_SQL = rank_case("NEW.required_role")
RANK_GRANT_G_ROLE_SQL = rank_case("g.admin_role")
REQUIRED_ROLE_BOUND_SQL = required_role_case("action_kind")

GRANT_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ck_admin_role_grants_principal", _nonblank("principal_subject", 255)),
    ("ck_admin_role_grants_role_valid", f"admin_role IN ({_sql_list(ADMIN_ROLES)})"),
    ("ck_admin_role_grants_status_valid", "status IN ('active','revoked')"),
    ("ck_admin_role_grants_granted_by", _nonblank("granted_by", 200)),
    (
        "ck_admin_role_grants_provenance",
        "granted_by_provenance = 'operator_admin_session_unverified'",
    ),
)

ACTION_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ck_admin_actions_kind_valid", f"action_kind IN ({_sql_list(ADMIN_ACTION_KINDS)})"),
    ("ck_admin_actions_actor_principal", _nonblank("actor_principal", 255)),
    (
        "ck_admin_actions_actor_provenance",
        "actor_provenance IN ('caller_supplied_unverified','request_authenticated')",
    ),
    ("ck_admin_actions_required_role_valid", f"required_role IN ({_sql_list(ADMIN_ROLES)})"),
    (
        "ck_admin_actions_actor_role_valid",
        f"actor_role IS NULL OR actor_role IN ({_sql_list(ADMIN_ROLES)})",
    ),
    ("ck_admin_actions_decision_valid", f"decision IN ({_sql_list(DECISIONS)})"),
    ("ck_admin_actions_ruleset_version", f"ruleset_version = '{RULESET_VERSION}'"),
    ("ck_admin_actions_required_role_bound", f"required_role = {REQUIRED_ROLE_BOUND_SQL}"),
    (
        "ck_admin_actions_allowed_rank",
        f"decision <> 'allowed' OR ({RANK_ACTOR_ROLE_SQL} >= {RANK_REQUIRED_ROLE_SQL})",
    ),
    (
        "ck_admin_actions_insufficient_rank",
        "decision <> 'refused_insufficient_role' OR "
        f"({RANK_ACTOR_ROLE_SQL} < {RANK_REQUIRED_ROLE_SQL})",
    ),
    (
        "ck_admin_actions_role_presence",
        "(actor_role IS NOT NULL) = "
        "(decision IN ('allowed','refused_insufficient_role'))",
    ),
    (
        "ck_admin_actions_provenance_partition",
        "(actor_provenance = 'caller_supplied_unverified') = "
        "(decision = 'refused_unauthenticated_actor')",
    ),
)

CHANGE_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ck_admin_policy_changes_previous_level", "previous_autonomy_level BETWEEN 0 AND 5"),
    ("ck_admin_policy_changes_new_level", "new_autonomy_level BETWEEN 0 AND 5"),
    ("ck_admin_policy_changes_override_key_count", "override_key_count >= 0"),
)

EVENT_KINDS = (
    "tenant_suspended",
    "tenant_reinstated",
    "organization_suspended",
    "organization_reinstated",
    "role_granted",
    "role_revoked",
)

EVENT_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ck_tae_event_kind_valid", f"event_kind IN ({_sql_list(EVENT_KINDS)})"),
    (
        "ck_tae_subject_principal",
        f"subject_principal IS NULL OR ({_nonblank('subject_principal', 255)})",
    ),
    (
        "ck_tae_admin_role_valid",
        f"admin_role IS NULL OR admin_role IN ({_sql_list(ADMIN_ROLES)})",
    ),
    ("ck_tae_performed_by", _nonblank("performed_by", 200)),
    (
        "ck_tae_performed_by_provenance",
        "performed_by_provenance = 'operator_admin_session_unverified'",
    ),
    (
        "ck_tae_role_shape",
        "(event_kind IN ('role_granted','role_revoked')) = "
        "(subject_principal IS NOT NULL AND admin_role IS NOT NULL AND "
        "admin_role_grant_id IS NOT NULL)",
    ),
)

ORG_STATUS_CHECK = (
    "ck_organizations_status_valid",
    "status IN ('active','suspended')",
)

CHECK_SQL_BY_NAME: dict[str, str] = dict(
    GRANT_CHECK_CONSTRAINTS
    + ACTION_CHECK_CONSTRAINTS
    + CHANGE_CHECK_CONSTRAINTS
    + EVENT_CHECK_CONSTRAINTS
    + (ORG_STATUS_CHECK,)
)
