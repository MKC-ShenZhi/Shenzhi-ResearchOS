"""Process-pinned deployment artifact. Secrets are resolved only from deployment injection."""
import json
import os
from functools import lru_cache
from pathlib import Path
from uuid import UUID
from urllib.parse import urlsplit

from agent_contracts.canonical import digest
from agent_contracts.management_config import ConfigSpec
from agent_app.errors import BusinessError


def config_error():
    return BusinessError(20004, '执行配置产物无效或部署凭据不可用', 503)


@lru_cache(maxsize=1)
def load_profile():
    name = os.getenv('AGENT_EXECUTION_CONFIG_FILE', '').strip()
    if not name:
        return None
    try:
        with Path(name).open('rb') as stream:
            raw = stream.read(512 * 1024 + 1)
        if len(raw) > 512 * 1024:
            raise ValueError('size')
        wrapper = json.loads(raw)
        spec = ConfigSpec.model_validate(wrapper['spec'])
        revision = str(UUID(wrapper['revision_id']))
        if wrapper['config_digest'] != spec.config_digest:
            raise ValueError('digest')
        if spec.build_revision != os.getenv('AGENT_BUILD_REVISION', '').strip():
            raise ValueError('build')
        return revision, spec
    except (ValueError, OSError, KeyError, TypeError):
        raise config_error() from None


def secret_environment(spec):
    destinations = set(os.getenv('AGENT_CONFIG_PROVIDER_ORIGINS', '').split())
    aliases = set(os.getenv('AGENT_CONFIG_SECRET_REFS', '').split())
    keys = {}
    for item in spec.providers:
        endpoint = urlsplit(item.base_url)
        origin = endpoint.scheme + '://' + endpoint.netloc
        if origin not in destinations or item.secret_ref not in aliases:
            raise config_error()
        value = os.getenv(item.secret_ref, '').strip()
        if item.enabled and not value:
            raise config_error()
        keys[item.secret_ref] = value
    return keys


def registry_for(spec):
    from agent_app.integrations.llm.registry import Catalog, ModelRegistry
    try:
        providers = [{**p.model_dump(exclude={'provider_id', 'secret_ref'}),
                      'id': p.provider_id, 'api_key_env': p.secret_ref} for p in spec.providers]
        models = []
        for model in spec.models:
            params = {}
            if model.thinking_enabled is not None:
                kind = model.capabilities.thinking
                if kind == 'enable_thinking':
                    params[kind] = model.thinking_enabled
                elif kind == 'thinking':
                    params[kind] = {'type': 'enabled' if model.thinking_enabled else 'disabled'}
                else:
                    raise config_error()
            models.append({**model.model_dump(exclude={'model_id', 'upstream_model_id', 'thinking_enabled'}),
                           'id': model.model_id, 'upstream_model': model.upstream_model_id, 'request_params': params})
        ordered = {'providers': sorted(providers, key=lambda p: p['id']),
                   'models': sorted(models, key=lambda m: m['id']), 'defaults': spec.defaults}
        return ModelRegistry(Catalog.model_validate(ordered), secret_environment(spec))
    except (ValueError, TypeError):
        raise config_error() from None


def route_identity(resolved, spec):
    provider = next((item for item in spec.providers if item.provider_id == resolved.provider.spec.id), None)
    if not provider:
        raise config_error()
    return digest({'provider_id': provider.provider_id, 'protocol': provider.protocol, 'base_url': provider.base_url})


def artifact_skills(spec):
    from agent_app.extensions.skills import SkillStore, _load_skill
    root = Path(os.getenv('AGENT_CONFIG_SKILL_ARTIFACT_ROOT', '')).resolve()
    if spec.skills and not os.getenv('AGENT_CONFIG_SKILL_ARTIFACT_ROOT', '').strip():
        raise config_error()
    skills = {}
    for item in spec.skills:
        name = item.id.removeprefix('skill:')
        if not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name):
            raise config_error()
        folder = root / item.digest.removeprefix('sha256:') / name
        try:
            if folder.resolve() != folder or not folder.is_dir():
                raise config_error()
            skill = _load_skill(folder, executable=False)
            if skill.resource_content_digest != item.digest:
                raise config_error()
        except (ValueError, OSError):
            raise config_error() from None
        skills[name] = skill
    return SkillStore(skills)
