"""Tenant-owned append-only Slice-51 cost-policy and forecast evidence."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_MONEY = Numeric(18, 6)
_PERCENT = Numeric(9, 4)
_HASH = r"^sha256:[0-9a-f]{64}$"
_POLICY_HASH = "sha256:067a1078f436686629e777384c70734eb0c7197554c8b637ea1784587ef2e7d5"
_INPUT_HASH = "sha256:421c35ca34b48aebdaa404404a60ab4b18b9de81608ee754798f6719613aca6d"
_FORECAST_HASH = "sha256:b853aecc7bfd79c5e061a22651285b0c3f1eaa56412c5cb9bddca314f040d705"


class CostForecastPolicyVersion(Base):
    __tablename__ = "cost_forecast_policy_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(
            "policy_contract_version='slice51.cost_policy.v1' "
            "AND source_provenance='caller_supplied_unverified_structured_cost_policy'",
            name="contract_provenance",
        ),
        CheckConstraint(
            f"policy_contract_hash='{_POLICY_HASH}' AND policy_digest ~ '{_HASH}'", name="hashes"
        ),
        CheckConstraint(
            "max_total_model_cost_usd>0 AND max_daily_model_cost_usd>0 "
            "AND max_cloud_spend_usd>0 AND max_ci_minutes_per_day>0 "
            "AND require_approval_above_forecast_percentage BETWEEN 0 AND 100",
            name="numeric_bounds",
        ),
        CheckConstraint(
            "stop_condition_count=4 AND cardinality(stop_conditions)=4 AND "
            "stop_conditions=ARRAY['budget_exceeded','repeated_failure_without_new_strategy',"
            "'tool_loop_detected','model_provider_outage_extended']::text[]",
            name="stop_conditions",
        ),
        CheckConstraint(
            "source_label IS NULL OR (char_length(source_label) BETWEEN 1 AND 255 "
            "AND btrim(source_label)<>'')",
            name="source_label",
        ),
        CheckConstraint(
            "evidence_ref IS NULL OR (char_length(evidence_ref) BETWEEN 1 AND 500 "
            "AND btrim(evidence_ref)<>'')",
            name="evidence_ref",
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_cfpv_id_project_tenant"),
        UniqueConstraint(
            "tenant_id", "project_id", "policy_digest", name="uq_cfpv_project_digest"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    policy_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    policy_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    policy_digest: Mapped[str] = mapped_column(Text, nullable=False)
    max_total_model_cost_usd: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    max_daily_model_cost_usd: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    max_cloud_spend_usd: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    max_ci_minutes_per_day: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    require_approval_above_forecast_percentage: Mapped[Decimal] = mapped_column(
        _PERCENT, nullable=False
    )
    cheap_first_for_low_risk: Mapped[bool] = mapped_column(Boolean, nullable=False)
    frontier_for_high_risk: Mapped[bool] = mapped_column(Boolean, nullable=False)
    use_cached_context_when_possible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stop_conditions: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    stop_condition_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    source_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CostForecastRun(Base):
    __tablename__ = "cost_forecast_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            ["release_candidates.id", "release_candidates.project_id", "release_candidates.tenant_id"],
            ondelete="RESTRICT",
            name="candidate_project_tenant",
        ),
        ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
            name="pack_project_tenant",
        ),
        ForeignKeyConstraint(
            ["policy_version_id", "project_id", "tenant_id"],
            [
                "cost_forecast_policy_versions.id",
                "cost_forecast_policy_versions.project_id",
                "cost_forecast_policy_versions.tenant_id",
            ],
            ondelete="RESTRICT",
            name="policy_project_tenant",
        ),
        ForeignKeyConstraint(
            ["budget_id", "project_id", "tenant_id"],
            ["budgets.id", "budgets.project_id", "budgets.tenant_id"],
            ondelete="RESTRICT",
            name="budget_project_tenant",
        ),
        CheckConstraint(
            "policy_contract_version='slice51.cost_policy.v1' "
            "AND input_contract_version='slice51.cost_forecast_input.v1' "
            "AND forecast_contract_version='slice51.cost_forecast.v1' "
            "AND execution_provenance='system_derived_cost_forecast'",
            name="contracts_provenance",
        ),
        CheckConstraint(
            f"policy_contract_hash='{_POLICY_HASH}' AND input_contract_hash='{_INPUT_HASH}' "
            f"AND forecast_contract_hash='{_FORECAST_HASH}' "
            f"AND (budget_digest IS NULL OR budget_digest ~ '{_HASH}') "
            f"AND (ledger_digest IS NULL OR ledger_digest ~ '{_HASH}') "
            f"AND (assumption_digest IS NULL OR assumption_digest ~ '{_HASH}') "
            f"AND (price_digest IS NULL OR price_digest ~ '{_HASH}') "
            f"AND (result_digest IS NULL OR result_digest ~ '{_HASH}') "
            f"AND input_digest ~ '{_HASH}' "
            f"AND (core_content_hash IS NULL OR core_content_hash ~ '{_HASH}')",
            name="hashes",
        ),
        CheckConstraint("outcome IN ('succeeded','failed','refused')", name="outcome"),
        CheckConstraint(
            "stop_reason IN ('ok','no_budget','budget_exceeded','daily_budget_exceeded')",
            name="stop_reason",
        ),
        CheckConstraint(
            "char_length(reason_code) BETWEEN 1 AND 128 AND btrim(reason_code)<>''",
            name="reason_code",
        ),
        CheckConstraint(
            "(budget_total_usd IS NULL OR budget_total_usd>0) "
            "AND (budget_daily_usd IS NULL OR budget_daily_usd>0) "
            "AND event_ref_count BETWEEN 0 AND 50000 "
            "AND input_line_count BETWEEN 0 AND 1000 AND model_line_count BETWEEN 0 AND 128 "
            "AND dimension_count BETWEEN 0 AND 6",
            name="bounds",
        ),
        CheckConstraint(
            "(outcome='succeeded' AND release_candidate_id IS NOT NULL "
            "AND evidence_pack_id IS NOT NULL AND policy_version_id IS NOT NULL "
            "AND budget_id IS NOT NULL AND core_content_hash IS NOT NULL "
            "AND budget_total_usd IS NOT NULL AND budget_daily_usd IS NOT NULL "
            "AND budget_digest IS NOT NULL AND ledger_digest IS NOT NULL "
            "AND assumption_digest IS NOT NULL AND price_digest IS NOT NULL "
            "AND result_digest IS NOT NULL AND event_ref_count>0 AND input_line_count>=9 "
            "AND dimension_count=6) OR "
            "(outcome IN ('failed','refused') AND event_ref_count=0 "
            "AND input_line_count=0 AND model_line_count=0 AND dimension_count=0 "
            "AND NOT all_dimensions_within AND NOT approval_required "
            "AND NOT evidence_consistent AND NOT gate_eligible)",
            name="result_shape",
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_cfr_id_project_tenant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_candidate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    evidence_pack_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    budget_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_utc_date: Mapped[date] = mapped_column(Date, nullable=False)
    policy_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    policy_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    input_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    core_content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_total_usd: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    budget_daily_usd: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    budget_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    ledger_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumption_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_digest: Mapped[str] = mapped_column(Text, nullable=False)
    stop_reason: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    execution_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    event_ref_count: Mapped[int] = mapped_column(Integer, nullable=False)
    input_line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    model_line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    dimension_count: Mapped[int] = mapped_column(Integer, nullable=False)
    all_dimensions_within: Mapped[bool] = mapped_column(Boolean, nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evidence_consistent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    gate_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CostForecastLedgerEventRef(Base):
    __tablename__ = "cost_forecast_ledger_event_refs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            ["cost_forecast_runs.id", "cost_forecast_runs.project_id", "cost_forecast_runs.tenant_id"],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        ForeignKeyConstraint(
            ["cost_event_id", "project_id", "tenant_id"],
            ["cost_events.id", "cost_events.project_id", "cost_events.tenant_id"],
            ondelete="RESTRICT",
            name="event_project_tenant",
        ),
        CheckConstraint("ordinal BETWEEN 1 AND 50000 AND amount_usd>=0", name="bounds"),
        CheckConstraint(
            "component IN ('model_inference','tool_execution','cloud_runtime','ci_cd',"
            "'storage_retrieval','monitoring','human_review','rework')",
            name="component",
        ),
        CheckConstraint(
            f"material_digest ~ '{_HASH}' AND source_provenance='db_bound_incurred_cost_events'",
            name="provenance_digest",
        ),
        UniqueConstraint("run_id", "ordinal", name="uq_cfler_run_ordinal"),
        UniqueConstraint("run_id", "cost_event_id", name="uq_cfler_run_event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    cost_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    component: Mapped[str] = mapped_column(Text, nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    material_digest: Mapped[str] = mapped_column(Text, nullable=False)
    source_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CostForecastInputLine(Base):
    __tablename__ = "cost_forecast_input_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            ["cost_forecast_runs.id", "cost_forecast_runs.project_id", "cost_forecast_runs.tenant_id"],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        CheckConstraint("ordinal BETWEEN 1 AND 1000", name="ordinal"),
        CheckConstraint(
            "line_kind IN ('component_remaining','model_price','ci_minutes_today')",
            name="kind",
        ),
        CheckConstraint(
            "(line_kind='component_remaining' AND component IS NOT NULL "
            "AND remaining_total_usd IS NOT NULL AND remaining_today_usd IS NOT NULL "
            "AND remaining_today_usd<=remaining_total_usd AND model_route_hash IS NULL "
            "AND remaining_input_tokens IS NULL AND remaining_output_tokens IS NULL "
            "AND remaining_today_input_tokens IS NULL AND remaining_today_output_tokens IS NULL "
            "AND input_rate_usd_per_1k IS NULL AND output_rate_usd_per_1k IS NULL "
            "AND ci_minutes IS NULL AND source_provenance='reported_cost_forecast_assumption') OR "
            "(line_kind='model_price' AND component IS NULL AND remaining_total_usd IS NULL "
            "AND remaining_today_usd IS NULL AND model_route_hash IS NOT NULL "
            "AND remaining_input_tokens IS NOT NULL AND remaining_output_tokens IS NOT NULL "
            "AND remaining_today_input_tokens IS NOT NULL AND remaining_today_output_tokens IS NOT NULL "
            "AND input_rate_usd_per_1k IS NOT NULL AND output_rate_usd_per_1k IS NOT NULL "
            "AND ci_minutes IS NULL AND source_provenance='operator_configured_price_card_snapshot') OR "
            "(line_kind='ci_minutes_today' AND component IS NULL AND remaining_total_usd IS NULL "
            "AND remaining_today_usd IS NULL AND model_route_hash IS NULL "
            "AND remaining_input_tokens IS NULL AND remaining_output_tokens IS NULL "
            "AND remaining_today_input_tokens IS NULL AND remaining_today_output_tokens IS NULL "
            "AND input_rate_usd_per_1k IS NULL AND output_rate_usd_per_1k IS NULL "
            "AND ci_minutes IS NOT NULL AND source_provenance='reported_cost_forecast_assumption')",
            name="shape",
        ),
        CheckConstraint(
            "component IS NULL OR component IN ('model_inference','tool_execution','cloud_runtime',"
            "'ci_cd','storage_retrieval','monitoring','human_review','rework')",
            name="component",
        ),
        CheckConstraint(
            f"(model_route_hash IS NULL OR model_route_hash ~ '{_HASH}') "
            f"AND line_digest ~ '{_HASH}'",
            name="route_hash",
        ),
        CheckConstraint(
            "COALESCE(remaining_total_usd,0)>=0 AND COALESCE(remaining_today_usd,0)>=0 "
            "AND COALESCE(remaining_input_tokens,0)>=0 AND COALESCE(remaining_output_tokens,0)>=0 "
            "AND COALESCE(remaining_today_input_tokens,0)>=0 "
            "AND COALESCE(remaining_today_output_tokens,0)>=0 "
            "AND COALESCE(input_rate_usd_per_1k,0)>=0 "
            "AND COALESCE(output_rate_usd_per_1k,0)>=0 AND COALESCE(ci_minutes,0)>=0",
            name="nonnegative",
        ),
        CheckConstraint(
            "COALESCE(remaining_today_input_tokens,0)<=COALESCE(remaining_input_tokens,0) "
            "AND COALESCE(remaining_today_output_tokens,0)<=COALESCE(remaining_output_tokens,0)",
            name="today_tokens",
        ),
        UniqueConstraint("run_id", "ordinal", name="uq_cfil_run_ordinal"),
        UniqueConstraint("run_id", "line_kind", "component", name="uq_cfil_run_kind_component"),
        UniqueConstraint("run_id", "model_route_hash", name="uq_cfil_run_model_route"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    line_kind: Mapped[str] = mapped_column(Text, nullable=False)
    component: Mapped[str | None] = mapped_column(Text, nullable=True)
    remaining_total_usd: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    remaining_today_usd: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    model_route_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    remaining_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remaining_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remaining_today_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remaining_today_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_rate_usd_per_1k: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    output_rate_usd_per_1k: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    ci_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    derived_total_usd: Mapped[Decimal | None] = mapped_column(
        _MONEY,
        Computed(
            "CASE WHEN line_kind='model_price' THEN "
            "(remaining_input_tokens*input_rate_usd_per_1k + "
            "remaining_output_tokens*output_rate_usd_per_1k)/1000.0 "
            "WHEN line_kind='component_remaining' THEN remaining_total_usd ELSE NULL END"
        ),
        nullable=True,
    )
    derived_today_usd: Mapped[Decimal | None] = mapped_column(
        _MONEY,
        Computed(
            "CASE WHEN line_kind='model_price' THEN "
            "(remaining_today_input_tokens*input_rate_usd_per_1k + "
            "remaining_today_output_tokens*output_rate_usd_per_1k)/1000.0 "
            "WHEN line_kind='component_remaining' THEN remaining_today_usd ELSE NULL END"
        ),
        nullable=True,
    )
    source_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    line_digest: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CostForecastDimensionResult(Base):
    __tablename__ = "cost_forecast_dimension_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            ["cost_forecast_runs.id", "cost_forecast_runs.project_id", "cost_forecast_runs.tenant_id"],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        CheckConstraint("ordinal BETWEEN 1 AND 6", name="ordinal"),
        CheckConstraint(
            "dimension_code IN ('all_cost_total_usd','all_cost_daily_usd',"
            "'model_cost_total_usd','model_cost_daily_usd','cloud_spend_total_usd',"
            "'ci_minutes_daily')",
            name="dimension",
        ),
        CheckConstraint(
            f"forecast_value>=0 AND policy_limit>0 "
            f"AND approval_threshold BETWEEN 0 AND 100 AND dimension_digest ~ '{_HASH}'",
            name="bounds",
        ),
        UniqueConstraint("run_id", "ordinal", name="uq_cfdr_run_ordinal"),
        UniqueConstraint("run_id", "dimension_code", name="uq_cfdr_run_dimension"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    dimension_code: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_value: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    policy_limit: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    approval_threshold: Mapped[Decimal] = mapped_column(_PERCENT, nullable=False)
    dimension_digest: Mapped[str] = mapped_column(Text, nullable=False)
    utilization_percent: Mapped[Decimal] = mapped_column(
        _PERCENT,
        Computed("round((forecast_value/policy_limit)*100,4)"),
        nullable=False,
    )
    within_limit: Mapped[bool] = mapped_column(
        Boolean, Computed("forecast_value<policy_limit"), nullable=False
    )
    approval_triggered: Mapped[bool] = mapped_column(
        Boolean,
        Computed("round((forecast_value/policy_limit)*100,4)>approval_threshold"),
        nullable=False,
    )
    result_code: Mapped[str] = mapped_column(
        Text,
        Computed(
            "CASE WHEN forecast_value>=policy_limit THEN 'limit_reached_or_exceeded' "
            "WHEN round((forecast_value/policy_limit)*100,4)>approval_threshold "
            "THEN 'approval_required' ELSE 'within_limit' END"
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
