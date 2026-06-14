"""r5_declarable_categories

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-14

Slice 20 — R5 readiness. Makes ``human_approval_policy`` and ``production_authority``
declarable presence-only intake categories (non-authorizing). The only schema change is
expanding the ``intake_categories`` category CHECK from the 20-set to the 22-set; drop +
recreate the named constraint. No new table/column/grant/trigger. Downgrade restores the
20-set (and would fail if either new category has been declared — intentional, fail-safe).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_intake_categories_category_valid"

# 0019's 20 declarable categories.
_DECLARABLE_20 = (
    "project_manifest", "product_brief", "business_objectives", "scope_and_boundaries",
    "users_roles_permissions", "user_journeys_and_workflows", "non_functional_requirements",
    "domain_pack", "data_model_and_contracts", "integrations_and_external_systems",
    "existing_assets_and_repositories", "architecture_and_technology_constraints",
    "security_privacy_compliance", "environments_and_deployment_targets",
    "secrets_and_credentials_manifest", "tool_access_manifest",
    "operations_observability_support", "go_live_checklist",
    "risk_register_and_assurance_requirements", "prior_decisions_and_architecture_log",
)
# Slice 20 adds two presence-only declarable categories.
_DECLARABLE_22 = _DECLARABLE_20 + ("human_approval_policy", "production_authority")


def _sql(categories: tuple[str, ...]) -> str:
    return ", ".join(repr(c) for c in categories)


def upgrade() -> None:
    # op.f() => use the literal constraint name (0019 created it via op.f(); without this the
    # naming convention would re-prefix it to ck_intake_categories_ck_intake_categories_...).
    op.drop_constraint(op.f(_CONSTRAINT), "intake_categories", type_="check")
    op.create_check_constraint(
        op.f(_CONSTRAINT), "intake_categories", f"category IN ({_sql(_DECLARABLE_22)})"
    )


def downgrade() -> None:
    op.drop_constraint(op.f(_CONSTRAINT), "intake_categories", type_="check")
    op.create_check_constraint(
        op.f(_CONSTRAINT), "intake_categories", f"category IN ({_sql(_DECLARABLE_20)})"
    )
