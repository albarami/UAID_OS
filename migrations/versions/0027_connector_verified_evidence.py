"""connector_verified_evidence

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-23

Slice 28 — make the ``connector_verified`` branch-protection tier writable (via the connector path).
The provenance **column CHECK already allows both** values (``0025`` `ck_bps_provenance_valid`); only
the BEFORE INSERT guard forced ``caller_supplied_unverified``. This does a single
``CREATE OR REPLACE`` of ``branch_protection_snapshots_guard()`` to allow
``provenance IN ('caller_supplied_unverified','connector_verified')`` on INSERT, **preserving verbatim**
every other invariant (repo_ref slug + token denylist, JSON-array shape, per-element bounded strings,
and ``required_status_check_count = jsonb_array_length(...)``). No new table/column/grant.

App-layer enforces *when* the verified tier is used (only the connector path writes it); the DB widens
the allowed value but cannot itself attest authenticity (same caveat as Slices 26/27). ``downgrade``
restores the strict ``0025`` guard. Reversible.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SLUG_RE = "^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$"
_TOKENISH_RE = "/(gh[opusr]_|github_pat_)"

# Slice 28: allow the verified tier (the connector path is the sole writer, app-enforced).
_ALLOW = """IF NEW.provenance NOT IN ('caller_supplied_unverified','connector_verified') THEN
                RAISE EXCEPTION 'branch_protection_snapshots: provenance must be caller_supplied_unverified or connector_verified';
            END IF;"""
# 0025 original: only the unverified tier permitted.
_STRICT = """IF NEW.provenance <> 'caller_supplied_unverified' THEN
                RAISE EXCEPTION 'branch_protection_snapshots: provenance must be caller_supplied_unverified (connector_verified is unwritable this slice)';
            END IF;"""


def _guard(provenance_check: str) -> str:
    """The 0025 guard body, parameterized only on the INSERT provenance rule (all else verbatim)."""
    return f"""
        CREATE OR REPLACE FUNCTION public.branch_protection_snapshots_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            {provenance_check}
            IF NEW.repo_ref !~ '{_SLUG_RE}' THEN
                RAISE EXCEPTION 'branch_protection_snapshots: repo_ref must be an owner/repo slug';
            END IF;
            IF NEW.repo_ref ~* '{_TOKENISH_RE}' THEN
                RAISE EXCEPTION 'branch_protection_snapshots: repo_ref must not contain a token prefix';
            END IF;
            IF jsonb_typeof(NEW.required_status_checks) <> 'array' THEN
                RAISE EXCEPTION 'branch_protection_snapshots: required_status_checks must be a JSON array';
            END IF;
            IF EXISTS (
                SELECT 1 FROM jsonb_array_elements(NEW.required_status_checks) AS elem(val)
                WHERE jsonb_typeof(val) <> 'string'
                   OR char_length(val #>> '{{}}') < 1
                   OR char_length(val #>> '{{}}') > 200
            ) THEN
                RAISE EXCEPTION 'branch_protection_snapshots: required_status_checks elements must be 1..200-char strings';
            END IF;
            IF NEW.required_status_check_count <> jsonb_array_length(NEW.required_status_checks) THEN
                RAISE EXCEPTION 'branch_protection_snapshots: required_status_check_count must equal jsonb_array_length(required_status_checks)';
            END IF;
            RETURN NEW;
        END
        $fn$
    """


def upgrade() -> None:
    op.execute(_guard(_ALLOW))


def downgrade() -> None:
    op.execute(_guard(_STRICT))
