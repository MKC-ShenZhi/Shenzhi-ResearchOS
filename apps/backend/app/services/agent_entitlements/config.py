"""Fail-closed deployment configuration. No production values or keys in code."""
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .service import Entitlements, require


def entitlement_service():
    issuer, audience = os.getenv('AGENT_GRANT_ISSUER', ''), os.getenv('AGENT_AUDIENCE', '')
    require(issuer and audience, 'AUTHORIZATION_ENVIRONMENT_UNCONFIGURED', 503)
    key_path, kid = os.getenv('AGENT_GRANT_PRIVATE_KEY_FILE', ''), os.getenv('AGENT_GRANT_SIGNING_KID', '')
    key = None
    if key_path and kid:
        key = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)
        require(isinstance(key, Ed25519PrivateKey), 'SIGNING_ALGORITHM_INVALID', 503)
    return Entitlements(issuer=issuer, audience=audience, kid=kid or None, private_key=key)
