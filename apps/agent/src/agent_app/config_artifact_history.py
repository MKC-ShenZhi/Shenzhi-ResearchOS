"""Read immutable, revision-registered evidence without loading executable code."""
import json
import os
from pathlib import Path

from agent_contracts.canonical import digest, request_digest_v1
from agent_app.config_deployment import view
from agent_app.control.metering import GateDenied

MAX_TEXT = 65_536
MAX_RESOURCE = 4 * 1024 * 1024


def root_path(setting):
    value = os.getenv(setting, '').strip()
    if not value:
        raise FileNotFoundError
    return Path(value).resolve(strict=True)


def read_bytes(path, maximum):
    if path.is_symlink() or path.resolve(strict=True) != path or not path.is_file():
        raise ValueError('unsafe artifact')
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('oversize artifact')
    return data


def tool_snapshot(item):
    if not item.metadata_digest:
        return {'state': 'unavailable'}
    root = root_path('AGENT_CONFIG_TOOL_METADATA_ROOT')
    path = root / (item.metadata_digest.removeprefix('sha256:') + '.json')
    payload = json.loads(read_bytes(path, MAX_TEXT))
    if (not isinstance(payload, dict) or set(payload) != {'description', 'parameters_schema', 'dependency_digests'}
            or not isinstance(payload['description'], str) or not isinstance(payload['parameters_schema'], dict)
            or not isinstance(payload['dependency_digests'], list)
            or digest(payload) != item.metadata_digest):
        raise ValueError('invalid tool snapshot')
    return {'state': 'available', **payload, 'schema_digest': request_digest_v1(payload['parameters_schema']),
            'implementation_digest': item.implementation_digest}


def skill_snapshot(item, resource):
    name = item.id.removeprefix('skill:')
    if not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name):
        raise ValueError('invalid skill name')
    root = root_path('AGENT_CONFIG_SKILL_ARTIFACT_ROOT') / item.digest.removeprefix('sha256:') / name
    if root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError('invalid skill root')
    hashes = []
    resources = []
    preview = None
    total = 0
    scanned = 0
    for path in sorted(root.rglob('*')):
        scanned += 1
        relative = path.relative_to(root)
        if scanned > 1000 or path.is_symlink() or path.resolve(strict=True) != path:
            raise ValueError('invalid skill tree')
        if any(part in ('__pycache__', '.git', '.venv') for part in relative.parts) or path.is_dir():
            continue
        content = read_bytes(path, MAX_RESOURCE)
        total += len(content)
        if total > 16 * MAX_RESOURCE:
            raise ValueError('oversize skill tree')
        import hashlib
        file_digest = 'sha256:' + hashlib.sha256(content).hexdigest()
        label = relative.as_posix()
        hashes.append([label, file_digest])
        if label != 'SKILL.md' and relative.parts[0] not in ('references', 'scripts'):
            continue
        kind = 'script' if relative.parts[0] == 'scripts' else 'document'
        resources.append({'id': digest(label), 'name': label, 'digest': file_digest, 'kind': kind, 'size': len(content)})
        if resource == digest(label) and kind == 'document' and len(content) <= MAX_TEXT:
            preview = content.decode('utf-8')
    if digest(hashes) != item.digest:
        raise ValueError('skill digest mismatch')
    if resource and preview is None:
        raise GateDenied('RESOURCE_NOT_AVAILABLE', 404)
    return {'state': 'available', 'resources': resources, 'preview': preview}


def read_snapshot(kind, ref, resource):
    try:
        return tool_snapshot(ref) if kind == 'tool' else skill_snapshot(ref, resource)
    except FileNotFoundError:
        return {'state': 'unavailable'}
    except (OSError, ValueError, TypeError):
        return {'state': 'invalid'}


async def artifact_history(revision, kind, artifact, resource):
    import asyncio
    selected = await view(str(revision))
    refs = selected.spec.tools if kind == 'tool' else selected.spec.skills
    ref = next((item for item in refs if item.id == artifact), None)
    if ref is None:
        raise GateDenied('RESOURCE_NOT_REGISTERED_FOR_REVISION', 404)
    snapshot = await asyncio.to_thread(read_snapshot, kind, ref, resource)
    return {'artifact_id': ref.id, 'digest': ref.digest, **snapshot}
