"""Pure Slice-43 test-oracle contracts and deterministic evaluators (spec §14).

Definitions are inert data under the versioned ``slice43.oracle.v1`` schema. Only
named, code-owned runners execute; prose and the template's ``custom`` tolerance
never execute. Persistence and trusted CI observation binding live outside this
module.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "slice43.oracle.v1"
IRR_IMPLEMENTATION = "fleiss_kappa_binary_v1"
MAX_DEFINITION_BYTES = 256_000
MAX_CASES = 1_000
MAX_CASE_REF = 128
MAX_TEXT = 2_000
MAX_RUBRIC_ITEMS = 32
MAX_REVIEWERS = 16

_POLICY = "illustrative_default_tune_per_project_risk"
_SPECIFIED_RUNNERS = {"canonical_json_exact", "boolean_true"}
_REFERENCE_RUNNERS = {"canonical_json_exact", "numeric_percentage"}
_SAMPLE_CLASSES = {"representative", "adversarial", "calibration", "other"}
_COMMON_FIELDS = {
    "schema_version",
    "type",
    "target_requirement",
    "runner_key",
    "sample_size",
    "sample_size_policy",
    "minimum_pass_rate",
    "minimum_pass_rate_policy",
    "tolerance",
    "cases",
}
_TYPE_FIELDS = {
    "specified": _COMMON_FIELDS | {"expected_behavior"},
    "reference": _COMMON_FIELDS | {"reference_source", "tolerance_value"},
    "judgment": _COMMON_FIELDS
    | {
        "inter_rater_reliability_minimum",
        "irr_policy",
        "rubric",
        "reviewers",
        "calibration_examples",
        "failure_cases_and_limits",
        "human_review_required",
    },
}


class InvalidOracleDefinition(ValueError):
    """A definition or observation is not safe/executable under Slice 43."""


@dataclass(frozen=True)
class OracleCase:
    case_ref: str
    expected: Any = None
    reference: Any = None
    sample_class: str | None = None


@dataclass(frozen=True)
class OracleDefinition:
    schema_version: str
    oracle_type: str
    target_requirement: str
    runner_key: str
    sample_size: int
    minimum_pass_rate: Decimal
    cases: tuple[OracleCase, ...]
    expected_behavior: str | None = None
    reference_source: str | None = None
    tolerance: str | None = None
    tolerance_value: Decimal | None = None
    irr_minimum: Decimal | None = None
    rubric: tuple[str, ...] = ()
    reviewers: tuple[str, ...] = ()
    calibration_examples: tuple[str, ...] = ()
    failure_cases_and_limits: tuple[str, ...] = ()
    human_review_required: bool = False


@dataclass(frozen=True)
class CaseResult:
    case_ref: str
    passed: bool
    result_kind: str
    expected_digest: str | None = None
    observed_digest: str | None = None
    reference_digest: str | None = None
    observed_numeric: Decimal | None = None
    reference_numeric: Decimal | None = None
    tolerance_numeric: Decimal | None = None
    deviation: Decimal | None = None


@dataclass(frozen=True)
class JudgmentDecision:
    passed: bool
    reason: str
    pass_rate: Decimal
    irr: Decimal
    unresolved_disagreement_count: int


def _text(name: str, value: Any, limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise InvalidOracleDefinition(f"{name} must be a non-blank string <= {limit} chars")
    return value.strip()


def _decimal(name: str, value: Any, *, minimum: Decimal, maximum: Decimal) -> Decimal:
    if isinstance(value, bool):
        raise InvalidOracleDefinition(f"{name} must be a finite number in [{minimum},{maximum}]")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise InvalidOracleDefinition(
            f"{name} must be a finite number in [{minimum},{maximum}]"
        ) from exc
    if not result.is_finite() or result < minimum or result > maximum:
        raise InvalidOracleDefinition(f"{name} must be a finite number in [{minimum},{maximum}]")
    return result


def _positive_int(name: str, value: Any, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not (1 <= value <= maximum):
        raise InvalidOracleDefinition(f"{name} must be an integer in [1,{maximum}]")
    return value


def _text_list(
    name: str,
    value: Any,
    *,
    minimum: int = 1,
    maximum: int = 32,
    item_limit: int = MAX_TEXT,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not (minimum <= len(value) <= maximum):
        raise InvalidOracleDefinition(f"{name} must contain {minimum}..{maximum} strings")
    result = tuple(_text(f"{name} item", item, item_limit) for item in value)
    if len(set(result)) != len(result):
        raise InvalidOracleDefinition(f"{name} must not contain duplicates")
    return result


def _json_safe(value: Any, name: str) -> None:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise InvalidOracleDefinition(f"{name} must be canonical JSON data") from exc
    if len(encoded.encode("utf-8")) > MAX_DEFINITION_BYTES:
        raise InvalidOracleDefinition(f"{name} exceeds {MAX_DEFINITION_BYTES} bytes")


def canonical_digest(value: Any) -> str:
    """Hash canonical JSON; mapping key order cannot change an exact verdict."""
    _json_safe(value, "value")
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _normalized_definition(definition: OracleDefinition) -> dict[str, Any]:
    common: dict[str, Any] = {
        "schema_version": definition.schema_version,
        "type": definition.oracle_type,
        "target_requirement": definition.target_requirement,
        "runner_key": definition.runner_key,
        "sample_size": definition.sample_size,
        "sample_size_policy": _POLICY,
        "minimum_pass_rate": str(definition.minimum_pass_rate.normalize()),
        "minimum_pass_rate_policy": _POLICY,
        "tolerance": definition.tolerance,
    }
    if definition.oracle_type == "specified":
        common["expected_behavior"] = definition.expected_behavior
        common["cases"] = [
            {
                "case_ref": case.case_ref,
                **({"expected": case.expected} if definition.runner_key == "canonical_json_exact" else {}),
            }
            for case in definition.cases
        ]
    elif definition.oracle_type == "reference":
        common["reference_source"] = definition.reference_source
        if definition.tolerance_value is not None:
            common["tolerance_value"] = str(definition.tolerance_value.normalize())
        common["cases"] = [
            {
                "case_ref": case.case_ref,
                "reference": (
                    str(
                        _decimal(
                            f"case {case.case_ref} reference",
                            case.reference,
                            minimum=Decimal("-1E100"),
                            maximum=Decimal("1E100"),
                        ).normalize()
                    )
                    if definition.runner_key == "numeric_percentage"
                    else case.reference
                ),
            }
            for case in definition.cases
        ]
    else:
        common.update(
            {
                "inter_rater_reliability_minimum": str(definition.irr_minimum.normalize()),
                "irr_policy": _POLICY,
                "rubric": list(definition.rubric),
                "reviewers": list(definition.reviewers),
                "calibration_examples": list(definition.calibration_examples),
                "failure_cases_and_limits": list(definition.failure_cases_and_limits),
                "human_review_required": definition.human_review_required,
                "cases": [
                    {"case_ref": case.case_ref, "sample_class": case.sample_class}
                    for case in definition.cases
                ],
            }
        )
    return common


def definition_hash(data: Mapping[str, Any] | OracleDefinition) -> str:
    """Hash the canonical validated definition, not caller field ordering or numeric spelling."""
    definition = data if isinstance(data, OracleDefinition) else validate_definition(data)
    return canonical_digest(_normalized_definition(definition))


def _cases(data: Mapping[str, Any], oracle_type: str, runner_key: str) -> tuple[OracleCase, ...]:
    raw = data.get("cases")
    if not isinstance(raw, list):
        raise InvalidOracleDefinition("cases must be a list")
    cases: list[OracleCase] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise InvalidOracleDefinition("each case must be an object")
        allowed_case_fields = {
            "specified": {"case_ref", "expected"}
            if runner_key == "canonical_json_exact"
            else {"case_ref"},
            "reference": {"case_ref", "reference"},
            "judgment": {"case_ref", "sample_class"},
        }[oracle_type]
        if set(item) != allowed_case_fields:
            raise InvalidOracleDefinition("unknown case fields or missing required fields")
        ref = _text("case_ref", item.get("case_ref"), MAX_CASE_REF)
        if ref in seen:
            raise InvalidOracleDefinition(f"duplicate case_ref: {ref}")
        seen.add(ref)
        if oracle_type == "specified":
            if runner_key == "canonical_json_exact" and "expected" not in item:
                raise InvalidOracleDefinition(f"specified exact case {ref} requires expected")
            expected = item.get("expected")
            if runner_key == "canonical_json_exact":
                _json_safe(expected, f"case {ref} expected")
            cases.append(OracleCase(ref, expected=expected))
        elif oracle_type == "reference":
            if "reference" not in item:
                raise InvalidOracleDefinition(f"reference case {ref} requires reference")
            reference = item["reference"]
            if runner_key == "canonical_json_exact":
                _json_safe(reference, f"case {ref} reference")
            else:
                _decimal(f"case {ref} reference", reference, minimum=Decimal("-1E100"), maximum=Decimal("1E100"))
            cases.append(OracleCase(ref, reference=reference))
        else:
            sample_class = item.get("sample_class")
            if sample_class not in _SAMPLE_CLASSES:
                raise InvalidOracleDefinition(f"case {ref} has invalid sample_class")
            cases.append(OracleCase(ref, sample_class=sample_class))
    return tuple(cases)


def validate_definition(data: Mapping[str, Any]) -> OracleDefinition:
    """Validate the ruled ``slice43.oracle.v1`` discriminated union, fail closed."""
    if not isinstance(data, Mapping):
        raise InvalidOracleDefinition("definition must be an object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise InvalidOracleDefinition(f"schema_version must be {SCHEMA_VERSION}")
    oracle_type = data.get("type")
    if oracle_type not in {"specified", "reference", "judgment"}:
        raise InvalidOracleDefinition("type must be specified, reference, or judgment")
    if data.get("tolerance") == "custom" or data.get("runner_key") == "custom":
        raise InvalidOracleDefinition("custom tolerance is unsupported this slice")
    expected_fields = _TYPE_FIELDS[oracle_type]
    if oracle_type == "reference" and data.get("runner_key") != "numeric_percentage":
        expected_fields = expected_fields - {"tolerance_value"}
    if set(data) != expected_fields:
        raise InvalidOracleDefinition("unknown definition fields or missing required fields")
    target = _text("target_requirement", data.get("target_requirement"), 128)
    sample_size = _positive_int("sample_size", data.get("sample_size"), MAX_CASES)
    pass_rate = _decimal(
        "minimum_pass_rate", data.get("minimum_pass_rate"), minimum=Decimal(0), maximum=Decimal(1)
    )
    _json_safe(dict(data), "definition")
    if data.get("sample_size_policy") != _POLICY:
        raise InvalidOracleDefinition(f"sample_size_policy must be {_POLICY}")
    if data.get("minimum_pass_rate_policy") != _POLICY:
        raise InvalidOracleDefinition(f"minimum_pass_rate_policy must be {_POLICY}")
    runner_key = _text("runner_key", data.get("runner_key"), 128)
    tolerance = data.get("tolerance")
    if oracle_type == "specified":
        if runner_key not in _SPECIFIED_RUNNERS:
            raise InvalidOracleDefinition(f"unsupported specified runner_key: {runner_key}")
        if tolerance != "exact":
            raise InvalidOracleDefinition("specified tolerance must be exact")
        expected_behavior = _text("expected_behavior", data.get("expected_behavior"))
        cases = _cases(data, oracle_type, runner_key)
        if len(cases) != sample_size:
            raise InvalidOracleDefinition("sample_size must equal the number of cases")
        return OracleDefinition(
            SCHEMA_VERSION,
            oracle_type,
            target,
            runner_key,
            sample_size,
            pass_rate,
            cases,
            expected_behavior=expected_behavior,
            tolerance=tolerance,
        )

    if oracle_type == "reference":
        if runner_key not in _REFERENCE_RUNNERS:
            raise InvalidOracleDefinition(f"unsupported reference runner_key: {runner_key}")
        source = _text("reference_source", data.get("reference_source"))
        if runner_key == "canonical_json_exact" and tolerance != "exact":
            raise InvalidOracleDefinition("canonical reference tolerance must be exact")
        if runner_key == "numeric_percentage" and tolerance != "percentage":
            raise InvalidOracleDefinition("numeric reference tolerance must be percentage")
        tolerance_value = None
        if runner_key == "numeric_percentage":
            tolerance_value = _decimal(
                "tolerance_value",
                data.get("tolerance_value"),
                minimum=Decimal(0),
                maximum=Decimal(1),
            )
        cases = _cases(data, oracle_type, runner_key)
        if len(cases) != sample_size:
            raise InvalidOracleDefinition("sample_size must equal the number of cases")
        return OracleDefinition(
            SCHEMA_VERSION,
            oracle_type,
            target,
            runner_key,
            sample_size,
            pass_rate,
            cases,
            reference_source=source,
            tolerance=tolerance,
            tolerance_value=tolerance_value,
        )

    if runner_key != "rubric_fleiss_kappa_v1":
        raise InvalidOracleDefinition(f"unsupported judgment runner_key: {runner_key}")
    if tolerance != "rubric":
        raise InvalidOracleDefinition("judgment tolerance must be rubric")
    irr = _decimal(
        "inter_rater_reliability_minimum",
        data.get("inter_rater_reliability_minimum"),
        minimum=Decimal("-1"),
        maximum=Decimal("1"),
    )
    if data.get("irr_policy") != _POLICY:
        raise InvalidOracleDefinition(f"irr_policy must be {_POLICY}")
    rubric = _text_list("rubric", data.get("rubric"), maximum=MAX_RUBRIC_ITEMS)
    reviewers = _text_list(
        "reviewers",
        data.get("reviewers"),
        minimum=2,
        maximum=MAX_REVIEWERS,
        item_limit=128,
    )
    calibration = _text_list("calibration_examples", data.get("calibration_examples"))
    limits = _text_list("failure_cases_and_limits", data.get("failure_cases_and_limits"))
    human = data.get("human_review_required")
    if not isinstance(human, bool):
        raise InvalidOracleDefinition("human_review_required must be a bool")
    cases = _cases(data, oracle_type, runner_key)
    if len(cases) != sample_size:
        raise InvalidOracleDefinition("sample_size must equal the number of cases")
    classes = {case.sample_class for case in cases}
    if not {"representative", "adversarial"}.issubset(classes):
        raise InvalidOracleDefinition("judgment cases require representative and adversarial samples")
    return OracleDefinition(
        SCHEMA_VERSION,
        oracle_type,
        target,
        runner_key,
        sample_size,
        pass_rate,
        cases,
        tolerance=tolerance,
        irr_minimum=irr,
        rubric=rubric,
        reviewers=reviewers,
        calibration_examples=calibration,
        failure_cases_and_limits=limits,
        human_review_required=human,
    )


def _observation_map(definition: OracleDefinition, observations: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        raise InvalidOracleDefinition("observations must be a sequence")
    mapped: dict[str, Mapping[str, Any]] = {}
    for observation in observations:
        if not isinstance(observation, Mapping):
            raise InvalidOracleDefinition("each observation must be an object")
        ref = _text("observation case_ref", observation.get("case_ref"), MAX_CASE_REF)
        if ref in mapped:
            raise InvalidOracleDefinition(f"duplicate observation case_ref: {ref}")
        mapped[ref] = observation
    expected = {case.case_ref for case in definition.cases}
    if set(mapped) != expected:
        raise InvalidOracleDefinition("observations must match the definition case set exactly")
    return mapped


def evaluate_specified(
    definition: OracleDefinition, observations: Sequence[Mapping[str, Any]]
) -> tuple[CaseResult, ...]:
    if definition.oracle_type != "specified":
        raise InvalidOracleDefinition("specified evaluator requires a specified definition")
    mapped = _observation_map(definition, observations)
    results: list[CaseResult] = []
    for case in definition.cases:
        observed = mapped[case.case_ref].get("observed")
        observed_digest = canonical_digest(observed)
        if definition.runner_key == "canonical_json_exact":
            expected_digest = canonical_digest(case.expected)
            passed = observed_digest == expected_digest
        else:
            expected_digest = canonical_digest(True)
            passed = observed is True
        results.append(
            CaseResult(
                case.case_ref,
                passed,
                "specified_exact",
                expected_digest=expected_digest,
                observed_digest=observed_digest,
            )
        )
    return tuple(results)


def evaluate_reference(
    definition: OracleDefinition, observations: Sequence[Mapping[str, Any]]
) -> tuple[CaseResult, ...]:
    if definition.oracle_type != "reference":
        raise InvalidOracleDefinition("reference evaluator requires a reference definition")
    mapped = _observation_map(definition, observations)
    results: list[CaseResult] = []
    for case in definition.cases:
        observed = mapped[case.case_ref].get("observed")
        if definition.runner_key == "canonical_json_exact":
            reference_digest = canonical_digest(case.reference)
            observed_digest = canonical_digest(observed)
            results.append(
                CaseResult(
                    case.case_ref,
                    reference_digest == observed_digest,
                    "reference_exact",
                    observed_digest=observed_digest,
                    reference_digest=reference_digest,
                )
            )
            continue
        reference = _decimal(
            f"case {case.case_ref} reference",
            case.reference,
            minimum=Decimal("-1E100"),
            maximum=Decimal("1E100"),
        )
        actual = _decimal(
            f"case {case.case_ref} observed",
            observed,
            minimum=Decimal("-1E100"),
            maximum=Decimal("1E100"),
        )
        if reference == 0:
            deviation = Decimal(0) if actual == 0 else Decimal("Infinity")
        else:
            deviation = abs(actual - reference) / abs(reference)
        tolerance = definition.tolerance_value or Decimal(0)
        results.append(
            CaseResult(
                case.case_ref,
                deviation <= tolerance,
                "reference_percentage",
                observed_numeric=actual,
                reference_numeric=reference,
                tolerance_numeric=tolerance,
                deviation=deviation,
            )
        )
    return tuple(results)


def fleiss_kappa(ratings: Mapping[str, Sequence[bool]]) -> Decimal:
    """Fleiss' kappa for a complete binary panel, rounded to six decimals."""
    if not ratings:
        raise InvalidOracleDefinition("Fleiss' kappa requires at least one case")
    panel_size: int | None = None
    agreements: list[Decimal] = []
    passed_total = 0
    for case_ref, labels in ratings.items():
        if not isinstance(labels, Sequence) or isinstance(labels, (str, bytes)):
            raise InvalidOracleDefinition(f"ratings for {case_ref} must be a sequence")
        if len(labels) < 2 or any(not isinstance(label, bool) for label in labels):
            raise InvalidOracleDefinition(f"ratings for {case_ref} require at least two bool labels")
        if panel_size is None:
            panel_size = len(labels)
        elif len(labels) != panel_size:
            raise InvalidOracleDefinition("Fleiss' kappa requires the same panel size for every case")
        passed = sum(labels)
        failed = len(labels) - passed
        passed_total += passed
        numerator = Decimal(passed * (passed - 1) + failed * (failed - 1))
        denominator = Decimal(len(labels) * (len(labels) - 1))
        agreements.append(numerator / denominator)
    assert panel_size is not None
    observed = sum(agreements, Decimal(0)) / Decimal(len(agreements))
    total = Decimal(len(ratings) * panel_size)
    p_pass = Decimal(passed_total) / total
    expected = p_pass * p_pass + (Decimal(1) - p_pass) * (Decimal(1) - p_pass)
    if expected == 1:
        kappa = Decimal(1) if observed == 1 else Decimal(0)
    else:
        kappa = (observed - expected) / (Decimal(1) - expected)
    return kappa.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def evaluate_judgment_ratings(
    definition: OracleDefinition, ratings: Mapping[str, Mapping[str, bool]]
) -> JudgmentDecision:
    if definition.oracle_type != "judgment":
        raise InvalidOracleDefinition("judgment evaluator requires a judgment definition")
    expected_cases = {case.case_ref for case in definition.cases}
    if set(ratings) != expected_cases:
        raise InvalidOracleDefinition("ratings must match the definition case set exactly")
    expected_reviewers = set(definition.reviewers)
    ordered: dict[str, list[bool]] = {}
    disagreements = 0
    passed = 0
    total = 0
    for case in definition.cases:
        case_ratings = ratings[case.case_ref]
        if set(case_ratings) != expected_reviewers:
            raise InvalidOracleDefinition("every judgment case requires the exact reviewer set")
        labels = [case_ratings[reviewer] for reviewer in definition.reviewers]
        if any(not isinstance(label, bool) for label in labels):
            raise InvalidOracleDefinition("judgment labels must be bool")
        if len(set(labels)) > 1:
            disagreements += 1
        passed += sum(labels)
        total += len(labels)
        ordered[case.case_ref] = labels
    irr = fleiss_kappa(ordered)
    pass_rate = (Decimal(passed) / Decimal(total)).quantize(Decimal("0.000001"))
    if definition.human_review_required:
        reason = "human_review_required_unavailable"
    elif disagreements:
        reason = "unresolved_disagreement"
    elif definition.irr_minimum is not None and irr < definition.irr_minimum:
        reason = "irr_below_floor"
    elif pass_rate < definition.minimum_pass_rate:
        reason = "pass_rate_below_floor"
    else:
        reason = "passed"
    return JudgmentDecision(reason == "passed", reason, pass_rate, irr, disagreements)
