"""request_auth_identity

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-23

Slice 27 — request-authentication → verified actor identity (cross-cutting enabler). Additive plus
two existing-object replacements (both reversible):

- ``tenant_api_keys`` gains ``principal_subject`` + ``actor_type`` (the verified principal the key
  represents; §23.4 human/machine). Existing keys are backfilled (``actor_type='service'``,
  ``principal_subject='legacy:'||id``), then set NOT NULL + CHECK-bounded.
- ``resolve_tenant_api_key(text)`` is **DROPped + recreated** to return ``(tenant_id,
  principal_subject, actor_type)`` (PostgreSQL forbids changing a function's return type via CREATE
  OR REPLACE). The D4 least-privilege model is restored verbatim (owner ``api_key_resolver``; PUBLIC
  revoked; ``uaid_app`` EXECUTE-only — still no direct SELECT on the table).
- ``approvals`` gains ``requested_by_provenance`` (requester provenance; ``approver_provenance`` is
  now resolver-only) + value CHECKs on both, constrained to the identity-axis tiers.
- The ``risk_acceptance_records`` guard is **CREATE OR REPLACE**d to ALLOW
  ``approver_provenance='request_authenticated'`` on INSERT, **preserving every other invariant**
  (status=active, approval_authority_source=approval_matrix, hard-refusal rejection, immutability).
  Actor-bound signer semantics are enforced in the repository, not the guard.

The ``request_authenticated`` tier is key-custody-based, NOT a human signature; it flips no A5 gate.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FN = "public.resolve_tenant_api_key(text)"

# risk_acceptance_records columns immutable after creation (verbatim from 0021).
_IMMUTABLE = (
    "id", "tenant_id", "project_id", "release_id", "issue_id", "severity",
    "affected_requirements", "reason_for_acceptance", "business_impact",
    "compensating_controls", "rollback_or_mitigation_plan", "evidence_links",
    "required_follow_up_ticket", "included_in_release_notes", "expiry_date", "owner",
    "approver", "accepted_by", "approval_authority_source", "blocking_category",
    "approver_provenance", "created_at",
)
_HARD_REFUSALS = ", ".join(
    f"'{c}'"
    for c in (
        "critical_security_blocker", "fake_done_finding",
        "missing_production_rollback", "missing_regulated_or_safety_authority",
    )
)


def _ra_guard(insert_provenance_check: str) -> str:
    """The risk_acceptance_records guard body, parameterized only on the INSERT provenance rule."""
    immutable_checks = "\n            OR ".join(
        f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in _IMMUTABLE
    )
    return f"""
        CREATE OR REPLACE FUNCTION public.risk_acceptance_records_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'active' THEN
                    RAISE EXCEPTION 'risk_acceptance_records must be created with status=active';
                END IF;
                {insert_provenance_check}
                IF NEW.approval_authority_source <> 'approval_matrix' THEN
                    RAISE EXCEPTION 'risk_acceptance_records approval_authority_source must be approval_matrix';
                END IF;
                IF NEW.blocking_category IN ({_HARD_REFUSALS}) THEN
                    RAISE EXCEPTION 'risk_acceptance_records: hard-refusal category cannot be accepted (%)',
                        NEW.blocking_category;
                END IF;
            ELSIF TG_OP = 'UPDATE' THEN
                IF {immutable_checks} THEN
                    RAISE EXCEPTION 'risk_acceptance_records: only status and updated_at are mutable';
                END IF;
                IF NEW.status IS DISTINCT FROM OLD.status THEN
                    IF OLD.status <> 'active'
                    OR NEW.status NOT IN ('expired', 'revoked', 'superseded') THEN
                        RAISE EXCEPTION 'risk_acceptance_records invalid status transition: % -> %',
                            OLD.status, NEW.status;
                    END IF;
                END IF;
            END IF;
            RETURN NEW;
        END
        $fn$
    """


# Slice 27: allow the verified tier (repo enforces actor-bound signer match).
_RA_INSERT_ALLOW = """IF NEW.approver_provenance NOT IN ('caller_supplied_unverified', 'request_authenticated') THEN
                    RAISE EXCEPTION 'risk_acceptance_records approver_provenance must be caller_supplied_unverified or request_authenticated';
                END IF;"""
# 0021 original: only the unverified tier permitted.
_RA_INSERT_STRICT = """IF NEW.approver_provenance <> 'caller_supplied_unverified' THEN
                    RAISE EXCEPTION 'risk_acceptance_records approver_provenance must be caller_supplied_unverified';
                END IF;"""


def upgrade() -> None:
    # --- 1) tenant_api_keys principal columns (added before the resolver that reads them) ---
    op.add_column("tenant_api_keys", sa.Column("principal_subject", sa.Text(), nullable=True))
    op.add_column("tenant_api_keys", sa.Column("actor_type", sa.Text(), nullable=True))
    op.execute(
        "UPDATE tenant_api_keys SET principal_subject = 'legacy:' || id::text, "
        "actor_type = 'service' WHERE principal_subject IS NULL"
    )
    op.alter_column("tenant_api_keys", "principal_subject", nullable=False)
    op.alter_column("tenant_api_keys", "actor_type", nullable=False)
    op.create_check_constraint(
        "principal_subject_bounded",
        "tenant_api_keys",
        "octet_length(principal_subject) BETWEEN 1 AND 255",
    )
    op.create_check_constraint(
        "actor_type_valid", "tenant_api_keys", "actor_type IN ('human', 'service')"
    )

    # --- 2) resolver: DROP + recreate as a 3-field row + restore D4 owner/grants verbatim ---
    op.execute(f"DROP FUNCTION {_FN}")
    op.execute(
        """
        CREATE FUNCTION public.resolve_tenant_api_key(
            p_key_hash text,
            OUT tenant_id uuid, OUT principal_subject text, OUT actor_type text
        ) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $fn$
            SELECT tenant_id, principal_subject, actor_type FROM public.tenant_api_keys
            WHERE key_hash = p_key_hash AND status = 'active'
            LIMIT 1
        $fn$
        """
    )
    op.execute(f"ALTER FUNCTION {_FN} OWNER TO api_key_resolver")
    op.execute(f"REVOKE ALL ON FUNCTION {_FN} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_FN} TO uaid_app")

    # --- 3) approvals: requester provenance + value CHECKs on both provenance columns ---
    op.add_column(
        "approvals",
        sa.Column(
            "requested_by_provenance",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'caller_supplied_unverified'"),
        ),
    )
    op.create_check_constraint(
        "requested_by_provenance_valid",
        "approvals",
        "requested_by_provenance IN ('caller_supplied_unverified', 'request_authenticated')",
    )
    op.create_check_constraint(
        "approver_provenance_valid",
        "approvals",
        "approver_provenance IN ('caller_supplied_unverified', 'request_authenticated')",
    )

    # --- 4) risk_acceptance guard: allow the verified tier on INSERT (other invariants preserved) ---
    op.execute(_ra_guard(_RA_INSERT_ALLOW))


def downgrade() -> None:
    # 4) restore the strict 0021 guard (only the unverified tier permitted on INSERT).
    op.execute(_ra_guard(_RA_INSERT_STRICT))

    # 3) drop approvals additions.
    op.drop_constraint("approver_provenance_valid", "approvals", type_="check")
    op.drop_constraint("requested_by_provenance_valid", "approvals", type_="check")
    op.drop_column("approvals", "requested_by_provenance")

    # 2) restore the scalar 0013 resolver (references only tenant_id) + grants.
    op.execute(f"DROP FUNCTION {_FN}")
    op.execute(
        """
        CREATE FUNCTION public.resolve_tenant_api_key(p_key_hash text) RETURNS uuid
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $fn$
            SELECT tenant_id FROM public.tenant_api_keys
            WHERE key_hash = p_key_hash AND status = 'active'
            LIMIT 1
        $fn$
        """
    )
    op.execute(f"ALTER FUNCTION {_FN} OWNER TO api_key_resolver")
    op.execute(f"REVOKE ALL ON FUNCTION {_FN} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_FN} TO uaid_app")

    # 1) drop tenant_api_keys principal columns (after the scalar resolver no longer needs them).
    op.drop_constraint("actor_type_valid", "tenant_api_keys", type_="check")
    op.drop_constraint("principal_subject_bounded", "tenant_api_keys", type_="check")
    op.drop_column("tenant_api_keys", "actor_type")
    op.drop_column("tenant_api_keys", "principal_subject")
