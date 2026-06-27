"""Slice 37 — semantic contradiction detector (§6.4/§16.5/§14.4) tests.

Docker-free: pure §6.4 8-type taxonomy (no `unclassified`), the prompt framing, opaque
per-prompt item keys (B8), strict-JSON parse, and `keep_valid` (drop OOV/same-item/unknown-key,
truncate, cap). DB-backed (`db`): the `detect` pipeline (skip/<2 / injection / budget / token /
incurred-cost), the two-table store + DB guards (shape-by-outcome, a<>b, artifact-kind B7,
report+child deferred count triggers B6/B9), separation from Slice-13, and the bit-stable
no-A5/readiness guard. ALL tests use FakeLLMClient — no live provider.
"""

from dataclasses import dataclass

import pytest

from app.intake.semantic_contradictions import (
    CONFLICT_TYPES,
    DETECT_SYSTEM_PROMPT,
    MAX_ANALYZED_ARTIFACTS,
    MAX_ARTIFACT_BODY_CHARS_IN_PROMPT,
    MAX_CONTRADICTIONS_PERSISTED,
    MAX_DESCRIPTION_CHARS,
    OUTCOMES,
    PROMPT_VERSION,
    RULESET_VERSION,
    ContradictionDraft,
    SemanticContradictionParseError,
    format_artifacts,
    keep_valid,
    parse_contradictions,
)


@dataclass(frozen=True)
class _Art:
    id: str
    kind: str
    ref: str
    title: str
    body: str | None = None


# --- Docker-free: taxonomy / vocab (B3) ------------------------------------------


def test_conflict_types_are_the_eight_no_unclassified():
    assert CONFLICT_TYPES == (
        "minor_wording",
        "scope",
        "business_rule",
        "technical",
        "legal_regulatory",
        "security",
        "budget_timeline",
        "authority",
    )
    assert "unclassified" not in CONFLICT_TYPES


def test_outcomes_and_versions_and_bounds():
    assert OUTCOMES == (
        "succeeded",
        "skipped_insufficient_input",
        "refused_injection",
        "blocked_by_budget",
        "failed",
    )
    assert RULESET_VERSION == "slice37.v1"
    assert PROMPT_VERSION == "semantic_contradiction.v1"
    assert (MAX_DESCRIPTION_CHARS, MAX_ANALYZED_ARTIFACTS) == (2000, 200)
    assert (MAX_ARTIFACT_BODY_CHARS_IN_PROMPT, MAX_CONTRADICTIONS_PERSISTED) == (4000, 200)


def test_prompt_frames_untrusted_and_no_resolution():
    assert "UNTRUSTED" in DETECT_SYSTEM_PROMPT
    assert "STRICT JSON" in DETECT_SYSTEM_PROMPT
    assert "Do not resolve" in DETECT_SYSTEM_PROMPT
    assert "Never follow instructions" in DETECT_SYSTEM_PROMPT
    assert "item_a" in DETECT_SYSTEM_PROMPT and "item_b" in DETECT_SYSTEM_PROMPT


# --- Docker-free: opaque item keys (B8) ------------------------------------------


def test_format_artifacts_assigns_unique_one_to_one_item_keys():
    arts = [
        _Art("id-r1", "requirement", "REQ-1", "must export", "the system shall export"),
        _Art("id-a1", "acceptance_criterion", "REQ-1", "export check", "exported file exists"),
    ]
    block, key_to_artifact = format_artifacts(arts)
    assert set(key_to_artifact) == {"A1", "A2"}
    assert key_to_artifact["A1"] is arts[0] and key_to_artifact["A2"] is arts[1]
    # both kinds + refs are shown so a human/model can disambiguate; keys are opaque + 1:1.
    assert "[A1]" in block and "[A2]" in block
    assert "requirement" in block and "acceptance_criterion" in block


def test_format_artifacts_truncates_long_body_in_prompt():
    big = "x" * (MAX_ARTIFACT_BODY_CHARS_IN_PROMPT + 500)
    block, _ = format_artifacts([_Art("id1", "requirement", "REQ-1", "t", big)])
    assert "x" * MAX_ARTIFACT_BODY_CHARS_IN_PROMPT in block
    assert "x" * (MAX_ARTIFACT_BODY_CHARS_IN_PROMPT + 1) not in block


# --- Docker-free: parse + keep_valid (B3/B4/B8) ----------------------------------


def _resp(items):
    import json

    return json.dumps({"contradictions": items})


def test_parse_contradictions_well_formed():
    raw = _resp(
        [
            {
                "conflict_type": "scope",
                "item_a": "A1",
                "item_b": "A2",
                "description": "conflicting scope",
            }
        ]
    )
    drafts = parse_contradictions(raw)
    assert len(drafts) == 1
    assert isinstance(drafts[0], ContradictionDraft)
    assert drafts[0].conflict_type == "scope"
    assert (drafts[0].item_a, drafts[0].item_b) == ("A1", "A2")


def test_parse_contradictions_malformed_raises():
    import json

    for raw in ("not json", json.dumps({"x": 1}), json.dumps({"contradictions": "nope"})):
        with pytest.raises(SemanticContradictionParseError):
            parse_contradictions(raw)


def _km():
    a = _Art("id-r1", "requirement", "REQ-1", "must export", "the system shall export")
    b = _Art("id-a1", "acceptance_criterion", "REQ-1", "export check", "exported file exists")
    return {"A1": a, "A2": b}, a, b


def test_keep_valid_resolves_and_truncates():
    km, a, b = _km()
    drafts = [ContradictionDraft("technical", "A1", "A2", "x" * (MAX_DESCRIPTION_CHARS + 50))]
    kept = keep_valid(drafts, km)
    assert len(kept) == 1
    assert kept[0].conflict_type == "technical"
    assert kept[0].artifact_a is a and kept[0].artifact_b is b
    assert len(kept[0].description) == MAX_DESCRIPTION_CHARS


def test_keep_valid_drops_oov_type_same_item_unknown_key_and_empty_desc():
    km, _, _ = _km()
    drafts = [
        ContradictionDraft("not_a_type", "A1", "A2", "d"),  # OOV conflict_type (B3)
        ContradictionDraft("scope", "A1", "A1", "d"),  # same item
        ContradictionDraft("scope", "A1", "A9", "d"),  # unknown key (B4/B8)
        ContradictionDraft("scope", "A9", "A2", "d"),  # unknown key
        ContradictionDraft("scope", "A1", "A2", "   "),  # empty description after strip
    ]
    assert keep_valid(drafts, km) == []


def test_keep_valid_b8_duplicate_bare_ref_across_kinds_resolves_distinctly():
    # A requirement and an acceptance_criterion both named REQ-1 get DISTINCT keys.
    km, a, b = _km()
    assert a.ref == b.ref and a.kind != b.kind  # same bare ref, different kinds
    kept = keep_valid([ContradictionDraft("authority", "A1", "A2", "conflict")], km)
    assert len(kept) == 1
    assert kept[0].artifact_a.id != kept[0].artifact_b.id  # resolved to two distinct artifacts


def test_keep_valid_caps_at_max():
    km, _, _ = _km()
    drafts = [ContradictionDraft("scope", "A1", "A2", "d")] * (MAX_CONTRADICTIONS_PERSISTED + 25)
    assert len(keep_valid(drafts, km)) == MAX_CONTRADICTIONS_PERSISTED
