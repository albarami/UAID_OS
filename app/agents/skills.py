"""Pure Skill Matching Engine primitives (Slice 38, §8) — no DB/I/O/LLM, Postgres-relational only.

The §8.2 skill graph is modeled relationally (no graph DB); this module is the deterministic core: the
§8.2 skill vocabulary, bounds/regexes, the **§8.3 verbatim transparent score** (with a full per-component
breakdown), and `build_squad` → the §8.4 project-squad manifest + per-(work-unit, agent) match records.

HONESTY (§8.3 transparency + the Slice-38 plan): `eval_performance` has **no source until Slice 40**, so it
is neutralized to `0.0` with `eval_source='absent_until_slice40'` — a score is a transparent **ranking aid,
NOT a qualification or authorization**. Persistence/audit live in `app.repositories.skills`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RULESET_VERSION = "slice38.v1"
EVAL_ABSENT = "absent_until_slice40"

# §8.2 (spec:721-749) — the 27 example skill categories, snake_case machine values (seed vocabulary).
SKILL_CATEGORIES: tuple[str, ...] = (
    "product_strategy",
    "business_analysis",
    "ux_design",
    "frontend_engineering",
    "backend_engineering",
    "mobile_engineering",
    "data_engineering",
    "ai_engineering",
    "prompt_engineering",
    "model_evaluation",
    "knowledge_graph_engineering",
    "workflow_automation",
    "api_integration",
    "devops",
    "security",
    "privacy",
    "domain_analysis",
    "compliance_mapping",
    "financial_modeling",
    "geospatial_systems",
    "formula_verification",
    "document_generation",
    "qa_automation",
    "accessibility",
    "performance_engineering",
    "release_management",
    "incident_response",
)

# §8.3 (spec:755-764) — VERBATIM weights (risk_penalty is subtracted, not weighted).
SCORE_WEIGHTS: dict[str, float] = {
    "capability_match": 0.30,
    "domain_fit": 0.15,
    "tool_access_fit": 0.15,
    "eval_performance": 0.20,
    "reviewer_availability": 0.10,
    "cost_latency_fit": 0.10,
}
# §8.1 risk dimension → deterministic penalty (declared work-unit risk_level).
RISK_PENALTY_BY_LEVEL: dict[str, float] = {"low": 0.0, "medium": 0.1, "high": 0.2}

COST_LATENCY_CLASSES: tuple[str, ...] = ("low", "medium", "high")
RISK_LEVELS: tuple[str, ...] = ("low", "medium", "high")

# Bounds / regexes (B6).
SKILL_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
TOOL_KEY_RE = re.compile(r"^[a-z][a-z0-9_.]{1,63}$")
DOMAIN_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
WORK_UNIT_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$")
MAX_WORK_UNITS = 128
MAX_REQUIRED_SKILLS_PER_UNIT = 32
MAX_REQUIRED_TOOLS_PER_UNIT = 32
MAX_PROVIDED_SKILLS = 128
MAX_PROVIDED_TOOLS = 64
MAX_DOMAINS = 32
MAX_CANDIDATES_SCORED_PER_UNIT = 32
MAX_MATCH_ROWS = 4096
MANIFEST_JSON_MAX_BYTES = 262144
MAX_REVIEWERS_PER_UNIT = 2


def validate_skill_key(key: str) -> str:
    if not isinstance(key, str) or not SKILL_KEY_RE.match(key):
        raise ValueError(f"invalid skill key: {key!r}")
    return key


@dataclass(frozen=True)
class WorkUnit:
    ref: str
    required_skills: tuple[str, ...]
    required_tools: tuple[str, ...] = ()
    domain: str | None = None
    risk_level: str = "low"
    cost_latency_fit: float = 0.0  # declared (caller_supplied_unverified)


@dataclass(frozen=True)
class AgentCapability:
    blueprint_ref: str
    role: str
    provided_skills: frozenset[str]
    provided_tools: frozenset[str] = frozenset()
    domains: frozenset[str] = frozenset()
    cost_latency_class: str = "medium"
    reviewer_skills: frozenset[str] = frozenset()  # skills this agent can review


@dataclass(frozen=True)
class MatchInputs:
    capability_match: float
    domain_fit: float
    tool_access_fit: float
    eval_performance: float
    reviewer_availability: float
    cost_latency_fit: float
    risk_penalty: float
    high_risk: bool
    eval_source: str


@dataclass(frozen=True)
class ScoreBreakdown:
    """The component values actually used + the total — persisted to `skill_matches` (transparency)."""

    capability_match: float
    domain_fit: float
    tool_access_fit: float
    eval_performance: float
    reviewer_availability: float
    cost_latency_fit: float  # effective (0.0 if zeroed by the high-risk rule)
    risk_penalty: float
    total_score: float
    eval_source: str


@dataclass(frozen=True)
class MatchRecord:
    work_unit_ref: str
    blueprint_ref: str
    breakdown: ScoreBreakdown

    # convenience for tests / persistence
    @property
    def reviewer_availability(self) -> float:
        return self.breakdown.reviewer_availability


@dataclass(frozen=True)
class ActiveAgent:
    blueprint_ref: str
    role: str
    assigned_work_units: tuple[str, ...]
    reviewers: tuple[str, ...]


@dataclass(frozen=True)
class SquadManifest:
    active_agents: tuple[ActiveAgent, ...] = ()
    missing_skills: tuple[str, ...] = ()
    agent_factory_requests: tuple[str, ...] = ()


def compute_capability_match(required_skills, provided_skills) -> float:
    required = set(required_skills)
    if not required:
        return 0.0  # a work-unit with no required skills cannot be meaningfully matched
    return len(required & set(provided_skills)) / len(required)


def compute_tool_access_fit(required_tools, provided_tools) -> float:
    required = set(required_tools)
    if not required:
        return 1.0  # no tool needs ⇒ fully satisfied
    return len(required & set(provided_tools)) / len(required)


def _distinct_reviewers(work_unit: WorkUnit, builder_ref: str, capabilities) -> tuple[str, ...]:
    req = set(work_unit.required_skills)
    return tuple(
        sorted(
            c.blueprint_ref
            for c in capabilities
            if c.blueprint_ref != builder_ref and (c.reviewer_skills & req)
        )
    )


def compute_agent_score(inputs: MatchInputs) -> ScoreBreakdown:
    # §8.3 reliability rule (l.766): high-risk work zeroes cost/latency before the weighted sum.
    effective_cost = 0.0 if inputs.high_risk else inputs.cost_latency_fit
    total = (
        inputs.capability_match * SCORE_WEIGHTS["capability_match"]
        + inputs.domain_fit * SCORE_WEIGHTS["domain_fit"]
        + inputs.tool_access_fit * SCORE_WEIGHTS["tool_access_fit"]
        + inputs.eval_performance * SCORE_WEIGHTS["eval_performance"]
        + inputs.reviewer_availability * SCORE_WEIGHTS["reviewer_availability"]
        + effective_cost * SCORE_WEIGHTS["cost_latency_fit"]
        - inputs.risk_penalty
    )
    return ScoreBreakdown(
        capability_match=inputs.capability_match,
        domain_fit=inputs.domain_fit,
        tool_access_fit=inputs.tool_access_fit,
        eval_performance=inputs.eval_performance,
        reviewer_availability=inputs.reviewer_availability,
        cost_latency_fit=effective_cost,
        risk_penalty=inputs.risk_penalty,
        total_score=round(total, 6),
        eval_source=inputs.eval_source,
    )


def _validate_work_units(work_units) -> None:
    if len(work_units) > MAX_WORK_UNITS:
        raise ValueError(f"too many work units (> {MAX_WORK_UNITS})")
    for wu in work_units:
        if not WORK_UNIT_REF_RE.match(wu.ref):
            raise ValueError(f"invalid work_unit ref: {wu.ref!r}")
        if not wu.required_skills or len(wu.required_skills) > MAX_REQUIRED_SKILLS_PER_UNIT:
            raise ValueError(
                f"work_unit {wu.ref}: 1..{MAX_REQUIRED_SKILLS_PER_UNIT} required skills"
            )
        if len(wu.required_tools) > MAX_REQUIRED_TOOLS_PER_UNIT:
            raise ValueError(f"work_unit {wu.ref}: too many required tools")
        if wu.risk_level not in RISK_LEVELS:
            raise ValueError(f"work_unit {wu.ref}: invalid risk_level {wu.risk_level!r}")


def build_squad(work_units, capabilities) -> tuple[SquadManifest, tuple[MatchRecord, ...]]:
    """Deterministic §8.4 squad manifest + the per-(work-unit, candidate) §8.3 match records."""
    _validate_work_units(work_units)
    all_provided: set[str] = (
        set().union(*(c.provided_skills for c in capabilities)) if capabilities else set()
    )

    assignments: dict[str, dict] = {}
    missing_skills: list[str] = []
    factory_requests: list[str] = []
    matches: list[MatchRecord] = []

    def _flag_missing(token: str, request: str) -> None:
        if token not in missing_skills:
            missing_skills.append(token)
            factory_requests.append(request)

    for wu in work_units:
        for skill in wu.required_skills:
            if skill not in all_provided:
                _flag_missing(skill, f"create_agent_for:{skill}")

        candidates = sorted(
            (c for c in capabilities if c.provided_skills & set(wu.required_skills)),
            key=lambda c: c.blueprint_ref,
        )[:MAX_CANDIDATES_SCORED_PER_UNIT]
        if not candidates:
            continue

        scored: list[tuple[AgentCapability, ScoreBreakdown, tuple[str, ...]]] = []
        for c in candidates:
            reviewers = _distinct_reviewers(wu, c.blueprint_ref, capabilities)
            inputs = MatchInputs(
                capability_match=compute_capability_match(wu.required_skills, c.provided_skills),
                domain_fit=1.0 if (wu.domain and wu.domain in c.domains) else 0.0,
                tool_access_fit=compute_tool_access_fit(wu.required_tools, c.provided_tools),
                eval_performance=0.0,
                reviewer_availability=1.0 if reviewers else 0.0,
                cost_latency_fit=wu.cost_latency_fit,
                risk_penalty=RISK_PENALTY_BY_LEVEL[wu.risk_level],
                high_risk=wu.risk_level == "high",
                eval_source=EVAL_ABSENT,
            )
            bd = compute_agent_score(inputs)
            scored.append((c, bd, reviewers))
            matches.append(MatchRecord(wu.ref, c.blueprint_ref, bd))

        scored.sort(key=lambda t: (-t[1].total_score, t[0].blueprint_ref))
        best_cap, _, best_reviewers = scored[0]
        slot = assignments.setdefault(
            best_cap.blueprint_ref, {"role": best_cap.role, "work_units": [], "reviewers": []}
        )
        slot["work_units"].append(wu.ref)
        if best_reviewers:
            for r in best_reviewers[:MAX_REVIEWERS_PER_UNIT]:
                if r not in slot["reviewers"]:
                    slot["reviewers"].append(r)
        else:
            # B5 — no distinct capable reviewer ⇒ flag + factory request; never self-review (§2.2).
            for skill in wu.required_skills:
                _flag_missing(f"reviewer:{skill}", f"create_reviewer_for:{skill}")

    if len(matches) > MAX_MATCH_ROWS:
        raise ValueError(f"too many match rows (> {MAX_MATCH_ROWS})")

    active_agents = tuple(
        ActiveAgent(ref, info["role"], tuple(info["work_units"]), tuple(info["reviewers"]))
        for ref, info in sorted(assignments.items())
    )
    manifest = SquadManifest(active_agents, tuple(missing_skills), tuple(factory_requests))
    return manifest, tuple(matches)
