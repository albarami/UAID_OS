"""Ed25519 signing boundary for Slice-60 export bundles.

The only module that imports ``cryptography``. Public helpers enforce trusted-key
resolution; raw crypto is private and explicitly unchecked. The private seed is
never a verification input.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from app.config import settings
from app.release.export_bundle import (
    MAX_SIGNING_KEY_ID,
    SIGNING_KEY_NOT_CONFIGURED,
    SIGNING_KEY_NOT_SELF_CONSISTENT,
    ExportBundleError,
)

_SEED_BYTES = 32
_PUBLIC_BYTES = 32
_SIGNATURE_BYTES = 64
_SIGNATURE_B64_RE = re.compile(r"^[A-Za-z0-9+/]{86}==$")
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")


def _b64decode_strict(value: str, *, expected_length: int) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ExportBundleError("base64_invalid") from exc
    if len(raw) != expected_length:
        raise ExportBundleError("base64_length_invalid")
    if base64.b64encode(raw).decode("ascii") != value:
        raise ExportBundleError("base64_non_canonical")
    return raw


def validate_signature_b64(value: str) -> bytes:
    """Decode a strict 88-character Ed25519 signature or raise."""
    if not isinstance(value, str) or _SIGNATURE_B64_RE.fullmatch(value) is None:
        raise ExportBundleError("signature_b64_invalid")
    return _b64decode_strict(value, expected_length=_SIGNATURE_BYTES)


def encode_signature_b64(signature: bytes) -> str:
    """Return canonical standard-base64 of a 64-byte signature."""
    if len(signature) != _SIGNATURE_BYTES:
        raise ExportBundleError("signature_length_invalid")
    encoded = base64.b64encode(signature).decode("ascii")
    if _SIGNATURE_B64_RE.fullmatch(encoded) is None:
        raise ExportBundleError("signature_b64_invalid")
    return encoded


def _sign_bytes_unchecked(seed: bytes, data: bytes) -> bytes:
    """Sign ``data`` with the 32-byte seed. Callers must already have validated custody."""
    key = Ed25519PrivateKey.from_private_bytes(seed)
    return key.sign(data)


def _verify_signature_unchecked(public_key: bytes, signature: bytes, data: bytes) -> bool:
    """Return whether ``signature`` is a valid Ed25519 signature over ``data``."""
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, data)
    except (InvalidSignature, ValueError):
        return False
    return True


def derived_public_key(seed: bytes) -> bytes:
    """Return the 32-byte public key derived from a 32-byte seed."""
    key = Ed25519PrivateKey.from_private_bytes(seed)
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def load_trusted_keys(raw: str | None = None) -> Mapping[str, bytes]:
    """Parse ``key_id=base64_pubkey`` comma-separated operator map. Fail closed."""
    text = settings.evidence_signing_trusted_keys if raw is None else raw
    if not isinstance(text, str) or not text.strip():
        return {}
    parsed: dict[str, bytes] = {}
    for segment in text.split(","):
        item = segment.strip()
        if not item:
            continue
        if "=" not in item:
            raise ExportBundleError("trusted_keys_invalid")
        key_id, _, encoded = item.partition("=")
        key_id = key_id.strip()
        encoded = encoded.strip()
        if not key_id or len(key_id) > MAX_SIGNING_KEY_ID or _KEY_ID_RE.fullmatch(key_id) is None:
            raise ExportBundleError("trusted_keys_invalid")
        if key_id in parsed:
            raise ExportBundleError("trusted_keys_duplicate")
        try:
            parsed[key_id] = _b64decode_strict(encoded, expected_length=_PUBLIC_BYTES)
        except ExportBundleError as exc:
            raise ExportBundleError("trusted_keys_invalid") from exc
    return parsed


def load_signing_seed() -> tuple[bytes, str, bytes]:
    """Return ``(seed, key_id, derived_public)`` or raise a named refusal code."""
    seed_b64 = settings.evidence_signing_private_key_b64
    key_id = settings.evidence_signing_key_id.strip() if settings.evidence_signing_key_id else ""
    if not seed_b64.strip() or not key_id:
        raise ExportBundleError(SIGNING_KEY_NOT_CONFIGURED)
    if len(key_id) > MAX_SIGNING_KEY_ID or _KEY_ID_RE.fullmatch(key_id) is None:
        raise ExportBundleError(SIGNING_KEY_NOT_CONFIGURED)
    try:
        seed = _b64decode_strict(seed_b64.strip(), expected_length=_SEED_BYTES)
    except ExportBundleError as exc:
        raise ExportBundleError(SIGNING_KEY_NOT_CONFIGURED) from exc
    try:
        public = derived_public_key(seed)
    except ValueError as exc:
        raise ExportBundleError(SIGNING_KEY_NOT_CONFIGURED) from exc
    try:
        trusted = load_trusted_keys()
    except ExportBundleError as exc:
        raise ExportBundleError(SIGNING_KEY_NOT_SELF_CONSISTENT) from exc
    pinned = trusted.get(key_id)
    if pinned is None or pinned != public:
        raise ExportBundleError(SIGNING_KEY_NOT_SELF_CONSISTENT)
    return seed, key_id, public


def sign_manifest_bytes(data: bytes) -> tuple[bytes, str]:
    """Sign manifest bytes with the operator seed after trusted-key self-check."""
    seed, key_id, _public = load_signing_seed()
    return _sign_bytes_unchecked(seed, data), key_id


def verify_manifest_signature(data: bytes, signature: bytes, signing_key_id: str) -> bool:
    """Verify ``signature`` using the operator-pinned key for ``signing_key_id``."""
    try:
        trusted = load_trusted_keys()
    except ExportBundleError:
        return False
    public = trusted.get(signing_key_id)
    if public is None:
        return False
    if not isinstance(signature, (bytes, bytearray)) or len(signature) != _SIGNATURE_BYTES:
        return False
    return _verify_signature_unchecked(public, bytes(signature), data)


def trusted_public_key(signing_key_id: str) -> bytes | None:
    """Return the operator-pinned public key for ``signing_key_id``, or ``None``."""
    try:
        trusted = load_trusted_keys()
    except ExportBundleError:
        return None
    return trusted.get(signing_key_id)


def encode_public_key_b64(public_key: bytes) -> str:
    """Return canonical standard-base64 of a 32-byte public key (tests only)."""
    if len(public_key) != _PUBLIC_BYTES:
        raise ExportBundleError("public_key_length_invalid")
    return base64.b64encode(public_key).decode("ascii")


def encode_seed_b64(seed: bytes) -> str:
    """Return canonical standard-base64 of a 32-byte seed (tests only)."""
    if len(seed) != _SEED_BYTES:
        raise ExportBundleError("seed_length_invalid")
    return base64.b64encode(seed).decode("ascii")


def generate_seed() -> tuple[bytes, bytes]:
    """Return a fresh ``(seed, public_key)`` pair (tests only)."""
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return seed, public
