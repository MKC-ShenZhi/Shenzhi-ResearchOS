"""Independent offline approval verified using deployment-pinned public keys."""
import base64
import json
import os
from datetime import datetime
from pathlib import Path
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from agent_contracts.canonical import canonical_json_v1
from agent_app.control.metering import GateDenied, now_utc


def approver(body, revision_id, validation_digest):
    if not body.external_proof:
        return body.actor
    try:
        proof = dict(body.external_proof)
        signature = base64.b64decode(proof.pop('signature'), validate=True)
        if set(proof) != {'approver', 'revision_id', 'validation_id', 'validation_digest', 'observed_at'}:
            raise ValueError()
        if (proof['revision_id'] != revision_id or proof['validation_id'] != str(body.validation_id)
                or proof['validation_digest'] != validation_digest):
            raise ValueError()
        observed = datetime.fromisoformat(proof['observed_at'])
        if observed.utcoffset() is None or not -30 <= (now_utc() - observed).total_seconds() <= 3600:
            raise ValueError()
        keys = json.loads(os.getenv('AGENT_CONFIG_APPROVER_PUBLIC_KEYS', '{}'))
        key = serialization.load_pem_public_key(Path(keys[proof['approver']]).read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError()
        key.verify(signature, canonical_json_v1(proof))
        return 'external-approver:' + proof['approver']
    except (KeyError, TypeError, ValueError, OSError, InvalidSignature):
        raise GateDenied('CONFIG_EXTERNAL_APPROVAL_INVALID', 403) from None
