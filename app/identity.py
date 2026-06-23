"""Verified actor identity (Slice 27, §2.2/§5.2/§7.x/§23.4) — pure, no I/O.

A request-authenticated **principal** bound to the bearer API key that authenticated the request.

**Honesty (non-negotiable).** ``request_authenticated`` means the request proved *possession of an
active API key bound to this principal* — strictly stronger than a caller-typed string, but **NOT** a
human signature, an approval-matrix authority (§24.1), or an evidence-pack signer (§15.4). It ranks
below a future human-signed / connector-verified tier and **never** authorizes go-live.

The verified tier is **app-stamped only**: ``actor_fields`` derives it from a real
:class:`AuthenticatedActor`, never from a caller-supplied payload field (the trust boundary, mirroring
Slice 26's "a caller may not assert ``connector_verified``").
"""

from __future__ import annotations

from dataclasses import dataclass

ACTOR_TYPES = ("human", "service")  # §23.4 human vs machine actors
# Identity-axis provenance. ``request_authenticated`` is the only app-writable value (custody-based).
IDENTITY_PROVENANCES = ("caller_supplied_unverified", "request_authenticated")
APP_WRITABLE = ("request_authenticated",)

CALLER_SUPPLIED_UNVERIFIED = "caller_supplied_unverified"
REQUEST_AUTHENTICATED = "request_authenticated"

_MAX_SUBJECT_BYTES = 255  # mirrors tenant_api_keys.label bound (app/models/tenant_api_key.py:24)


class InvalidActor(ValueError):
    """Raised when an actor subject/type fails validation (fail-closed)."""


@dataclass(frozen=True)
class AuthenticatedActor:
    """A principal proven by API-key custody. ``provenance`` is always the verified tier."""

    subject: str
    actor_type: str
    provenance: str = REQUEST_AUTHENTICATED


def validate_actor(subject: object, actor_type: object) -> AuthenticatedActor:
    """Validate + build an :class:`AuthenticatedActor`, or raise :class:`InvalidActor`."""
    if not isinstance(subject, str) or not subject.strip():
        raise InvalidActor("actor subject must be a non-empty string")
    if len(subject.encode("utf-8")) > _MAX_SUBJECT_BYTES:
        raise InvalidActor(f"actor subject must be 1..{_MAX_SUBJECT_BYTES} bytes")
    if actor_type not in ACTOR_TYPES:
        raise InvalidActor(f"actor_type must be one of {ACTOR_TYPES}")
    return AuthenticatedActor(subject=subject, actor_type=actor_type)


def actor_fields(actor: AuthenticatedActor | None, fallback_actor: str) -> tuple[str, str]:
    """Return ``(actor_label, provenance)``.

    With a real ``actor`` ⇒ ``(actor.subject, "request_authenticated")`` — the verified tier comes
    ONLY from here. Without ⇒ ``(fallback_actor, "caller_supplied_unverified")`` (current behavior).
    """
    if actor is not None:
        return actor.subject, REQUEST_AUTHENTICATED
    return fallback_actor, CALLER_SUPPLIED_UNVERIFIED
