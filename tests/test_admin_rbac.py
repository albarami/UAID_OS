"""Slice 63 pure RBAC probes (P-1…P-6)."""

from __future__ import annotations

import hashlib
import inspect
import pathlib
from uuid import uuid4

import pytest

from app.admin import policy_admin, rbac, tenant_admin
from app.admin.rbac import (
    ACTION_REQUIRED_ROLE,
    ADMIN_ACTION_KINDS,
    ADMIN_ROLES,
    DECISIONS,
    ROLE_RANKS,
    RULESET_VERSION,
    AdminActionRequest,
    AdminRbacError,
    RoleGrantView,
    evaluate_authorization,
)
from app.intake.readiness import RULESET_VERSION as READINESS_RULESET
from app.release.production_autonomy import A5_RULESET_VERSION

ROOT = pathlib.Path(__file__).resolve().parents[1]

FROZEN = {
    "app/release/production_autonomy.py": (
        "55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029"
    ),
    "app/intake/readiness.py": (
        "7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26"
    ),
    "app/runtime/control_loop.py": (
        "3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180"
    ),
    "app/tools/broker.py": (
        "20728181a65073d0ec5cacb63385fa2101760ec670e54621991eb24a97a33c57"
    ),
    "app/cost.py": "2dc1e1d1a0dcfb433af536b69bba926b5c74f3c028bda841d243416546819b43",
    "app/cost_forecast.py": (
        "0fb050597363bcb4af6393e48e8822d975094108f92f4c5770ea4656b3ce02b6"
    ),
    "app/llm/pricing.py": (
        "0693ab457daefd45fedbf3bd6df08e531568c89e2ca9a91dbd710c40febe5d59"
    ),
    "app/policy/matrix.py": (
        "c69a09ee8f910bffa839a8b75154dd3f3025fdb44c0c5aa0b9bfdd6e6f31a43f"
    ),
    "app/policy/engine.py": (
        "6269f250cc3fc621ed1f445175f79d9e5227f3ece4f0ea2546aa3fc1337a45c0"
    ),
    "app/tenancy.py": "cb7f9827bcf2c25fdd72ad29177e0f2fb6911b4ffbd7931ac1fe2cb939c2dbc1",
    "app/identity.py": "a76f99b85593e6d7ade9f71b6adb1a1ca81b3066436bb12ec9a04e7876897a09",
    "app/audit.py": "b44c45706c86ad4a55b45d81c43d9db0115e642267b2592c29d0649699c6c116",
    "app/api/auth.py": "86930b47f16f0a487518b2e232412ce61e7536d45bf963e7da7f7518d0fc76ab",
    "app/api/dashboard.py": (
        "752c1bb4e96c6681f16ea4314a3835603d0bb19c19dfc1b49b2e6207762d8a81"
    ),
    "app/repositories/api_keys.py": (
        "9dc80483746f0098efc65ead51267650404f9d315baa9f77706c66b836dcaeda"
    ),
    "app/models/tenant_api_key.py": (
        "c3753ea4648ecf857f16798754b7fcb07f091d81573bc99a61c305b21862d321"
    ),
    "app/models/tenant.py": (
        "d6b5cd28b139f1487eaa2d649ba443fe754964521635afd130d17f5a5a3594aa"
    ),
}

_FORBIDDEN_PARAMS = {
    "content",
    "document",
    "prompt",
    "body",
    "raw_key",
    "key_hash",
    "password",
}


def test_p1_vocabulary() -> None:
    assert ADMIN_ROLES == ("tenant_viewer", "tenant_operator", "tenant_admin")
    assert ROLE_RANKS == {"tenant_viewer": 1, "tenant_operator": 2, "tenant_admin": 3}
    assert set(ROLE_RANKS.values()) == {1, 2, 3}
    assert ADMIN_ACTION_KINDS == ("set_autonomy_policy", "tighten_autonomy_overrides")
    assert ACTION_REQUIRED_ROLE == {
        "set_autonomy_policy": "tenant_admin",
        "tighten_autonomy_overrides": "tenant_operator",
    }
    assert DECISIONS == (
        "allowed",
        "refused_unauthenticated_actor",
        "refused_no_grant",
        "refused_insufficient_role",
    )
    assert RULESET_VERSION == "slice63.v1"


def _req(kind: str = "set_autonomy_policy", *, provenance: str = "request_authenticated"):
    return AdminActionRequest(
        tenant_id=uuid4(),
        project_id=uuid4(),
        action_kind=kind,
        actor_principal="alice",
        actor_provenance=provenance,
    )


def _grant(tenant_id, role: str, *, status: str = "active") -> RoleGrantView:
    return RoleGrantView(
        tenant_id=tenant_id,
        principal_subject="alice",
        admin_role=role,
        status=status,
    )


def test_p2_evaluate_authorization() -> None:
    req = _req()
    admin = _grant(req.tenant_id, "tenant_admin")
    viewer = _grant(req.tenant_id, "tenant_viewer")
    operator = _grant(req.tenant_id, "tenant_operator")
    unverified = _req(provenance="caller_supplied_unverified")
    d = evaluate_authorization(unverified, (admin,))
    assert d.decision == "refused_unauthenticated_actor" and d.actor_role is None
    d = evaluate_authorization(unverified, ())
    assert d.decision == "refused_unauthenticated_actor"
    d = evaluate_authorization(req, ())
    assert d.decision == "refused_no_grant" and d.actor_role is None
    d = evaluate_authorization(req, (viewer,))
    assert d.decision == "refused_insufficient_role" and d.actor_role == "tenant_viewer"
    tighten = AdminActionRequest(
        tenant_id=req.tenant_id,
        project_id=req.project_id,
        action_kind="tighten_autonomy_overrides",
        actor_principal="alice",
        actor_provenance="request_authenticated",
    )
    d = evaluate_authorization(tighten, (operator,))
    assert d.decision == "allowed" and d.actor_role == "tenant_operator"
    d = evaluate_authorization(req, (operator,))
    assert d.decision == "refused_insufficient_role"
    d = evaluate_authorization(req, (viewer, admin))
    assert d.decision == "allowed" and d.actor_role == "tenant_admin"
    d = evaluate_authorization(tighten, (viewer, admin))
    assert d.decision == "allowed" and d.actor_role == "tenant_admin"
    d = evaluate_authorization(req, (_grant(req.tenant_id, "tenant_admin", status="revoked"),))
    assert d.decision == "refused_no_grant"


def test_p3_unknown_inputs_raise() -> None:
    req = _req()
    with pytest.raises(AdminRbacError):
        evaluate_authorization(
            AdminActionRequest(
                tenant_id=req.tenant_id,
                project_id=req.project_id,
                action_kind="not_a_kind",
                actor_principal="alice",
                actor_provenance="request_authenticated",
            ),
            (),
        )
    with pytest.raises(AdminRbacError):
        evaluate_authorization(req, (_grant(req.tenant_id, "org_admin"),))
    with pytest.raises(AdminRbacError):
        evaluate_authorization(
            AdminActionRequest(
                tenant_id=req.tenant_id,
                project_id=req.project_id,
                action_kind="set_autonomy_policy",
                actor_principal="   ",
                actor_provenance="request_authenticated",
            ),
            (),
        )
    with pytest.raises(AdminRbacError):
        evaluate_authorization(
            AdminActionRequest(
                tenant_id=req.tenant_id,
                project_id=req.project_id,
                action_kind="set_autonomy_policy",
                actor_principal="x" * 256,
                actor_provenance="request_authenticated",
            ),
            (),
        )


def test_p4_no_secret_parameters() -> None:
    for path in (ROOT / "app" / "admin").glob("*.py"):
        if path.name in {"guards_sql.py", "ddl.py", "policy_sql.py"}:
            continue
        source = path.read_text()
        for name in ("raw_key", "password", "override_value"):
            assert name not in source
    for module in (rbac, tenant_admin, policy_admin):
        source = inspect.getsource(module)
        for name in ("raw_key", "key_hash", "password"):
            assert name not in source
        for _name, fn in inspect.getmembers(module, inspect.isfunction):
            if fn.__module__ != module.__name__:
                continue
            params = set(inspect.signature(fn).parameters)
            assert params.isdisjoint(_FORBIDDEN_PARAMS)


def test_p5_frozen_hashes() -> None:
    assert len(FROZEN) == 17
    assert "app/policy/matrix.py" in FROZEN
    assert "app/policy/engine.py" in FROZEN
    for rel, digest in FROZEN.items():
        data = (ROOT / rel).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest


def test_p6_rulesets_and_go_live() -> None:
    assert A5_RULESET_VERSION == "slice54.v1"
    assert READINESS_RULESET == "slice20.v1"
    from app.release.production_autonomy import ProductionAutonomyReport

    report = ProductionAutonomyReport(project_id=str(uuid4()))
    assert report.to_dict()["can_go_live_autonomously"] is False
