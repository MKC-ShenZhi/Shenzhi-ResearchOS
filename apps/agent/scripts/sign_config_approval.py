"""Sign a reviewed validation on the approver's separate trusted machine."""
import argparse
import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from agent_contracts.canonical import canonical_json_v1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--private-key', required=True)
    parser.add_argument('--approver', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--validation', required=True)
    parser.add_argument('--validation-digest', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    import getpass
    passphrase = getpass.getpass('Private key passphrase (empty for unencrypted test key): ')
    key = serialization.load_pem_private_key(Path(args.private_key).read_bytes(),
                                             password=passphrase.encode() if passphrase else None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('Ed25519 key required')
    proof = dict(approver=args.approver, revision_id=args.revision, validation_id=args.validation,
                 validation_digest=args.validation_digest, observed_at=datetime.now(timezone.utc).isoformat())
    proof['signature'] = base64.b64encode(key.sign(canonical_json_v1(proof))).decode()
    with Path(args.output).open('x', encoding='utf-8') as stream:
        json.dump(proof, stream, indent=2)


if __name__ == '__main__':
    main()
