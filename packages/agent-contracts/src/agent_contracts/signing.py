"""Strict compact Ed25519 JWS primitives; key custody belongs to the services.

The shared package stores neither keys nor runtime configuration. cryptography
is an explicit service dependency, imported only when signatures are used.
"""
import base64
import json
from typing import TypeVar

from .canonical import canonical_json_v1, parse_canonical
from .v2 import BudgetGrant, GrantBindingReceipt, Signature

T = TypeVar('T', BudgetGrant, GrantBindingReceipt)
TYPES = {BudgetGrant: 'shenzhi-budget-grant', GrantBindingReceipt: 'shenzhi-grant-binding-receipt'}


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _decode(value: str) -> bytes:
    raw = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
    if _encode(raw) != value:
        raise ValueError('noncanonical base64url')
    return raw


def sign_claims(claims: dict, model: type[T], *, kid: str, private_key) -> T:
    claims = parse_canonical(canonical_json_v1(claims))
    header = _encode(canonical_json_v1({'alg': 'EdDSA', 'kid': kid, 'typ': TYPES[model]}))
    payload = _encode(canonical_json_v1(claims))
    signed = f'{header}.{payload}'.encode('ascii')
    signature = Signature(schema_version=1, kid=kid, alg='EdDSA', compact_jws=f'{header}.{payload}.{_encode(private_key.sign(signed))}')
    return model.model_validate({**claims, 'signature': signature})


def verify_signed(value: T, *, issuer: str, audience: str, public_keys: dict) -> T:
    """Check signed original bytes BEFORE parsing their strict schema."""
    signature = value.signature
    parts = signature.compact_jws.split('.')
    if len(parts) != 3:
        raise ValueError('invalid compact JWS')
    header_raw, payload_raw, sig_raw = map(_decode, parts)
    header = json.loads(header_raw)
    expected = {'alg': 'EdDSA', 'kid': signature.kid, 'typ': TYPES[type(value)]}
    if header != expected or canonical_json_v1(header) != header_raw or signature.alg != 'EdDSA':
        raise ValueError('untrusted JWS protected header')
    key = public_keys.get(signature.kid)
    if key is None:
        raise ValueError('unknown or revoked kid')
    try:
        key.verify(sig_raw, '.'.join(parts[:2]).encode('ascii'))
    except Exception as exc:
        raise ValueError('invalid JWS signature') from exc
    claims = parse_canonical(payload_raw)
    parsed = type(value).model_validate({**claims, 'signature': signature})
    if parsed != value or parsed.issuer != issuer or parsed.audience != audience:
        raise ValueError('signed claims, issuer or audience mismatch')
    if canonical_json_v1(value.model_dump(mode='json', exclude={'signature'})) != payload_raw:
        raise ValueError('noncanonical signed claims')
    return value
