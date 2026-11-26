"""Load declarative catalogs and trusted deployment overrides into one registry."""
from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from agent_app.integrations.llm.registry import (
    Capabilities, Catalog, ModelRegistry, ModelSpec, ProviderSpec, RegistryConfigError,
)

CATALOG_PATH = Path(__file__).with_name('catalog.json')


def _read_catalog(path: Path) -> Catalog:
    try:
        return Catalog.model_validate(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError, ValidationError):
        # Validation errors can contain input values. Never expose file contents.
        raise RegistryConfigError('无法加载声明文件，请检查文件和字段格式') from None


def model_definition(model_id: str, provider_id: str, upstream: str) -> ModelSpec:
    """Exact catalog lookup only; unknown models get conservative Chat capabilities."""
    catalog = _read_catalog(CATALOG_PATH)
    template = next((model for model in catalog.models
                     if model.provider_id == provider_id and model.upstream_model == upstream), None)
    if template:
        return template.model_copy(update={'id': model_id})
    return ModelSpec(id=model_id, provider_id=provider_id, upstream_model=upstream,
                     label=upstream, brand='zhipu' if provider_id == 'zhipu' else 'platform',
                     capabilities=Capabilities())


def load_registry() -> ModelRegistry:
    from agent_app.execution.config_profile import load_profile, registry_for
    profile = load_profile() if os.getenv('AGENT_EXECUTION_CONFIG_FILE') else None
    if profile:
        return registry_for(profile[1])
    catalog = _read_catalog(CATALOG_PATH)
    # Validate the source before replacement so duplicate/invalid built-ins cannot hide.
    ModelRegistry(catalog, {})
    providers = list(catalog.providers)
    models = list(catalog.models)
    aliases = dict(catalog.aliases)
    defaults = dict(catalog.defaults)
    path = os.getenv('AI_MODEL_REGISTRY_FILE', '').strip()
    if path:
        custom = _read_catalog(Path(path))
        for items, label in [(custom.models, 'Model'), (custom.providers, 'Provider')]:
            if len({item.id for item in items}) != len(items):
                raise RegistryConfigError(f'声明文件存在重复 {label} ID')
        # Replace in place: changing a definition must not change default priority.
        def merge(original, replacements):
            overrides = {item.id: item for item in replacements}
            return [overrides.pop(item.id, item) for item in original] + list(overrides.values())
        providers = merge(providers, custom.providers)
        models = merge(models, custom.models)
        aliases = {alias: target for alias, target in aliases.items()
                   if alias not in {model.id for model in custom.models}}
        aliases.update(custom.aliases)
        defaults.update(custom.defaults)
    # The naming convention works for built-in and file-defined providers alike.
    try:
        providers = [ProviderSpec.model_validate({**provider.model_dump(), 'base_url':
            os.getenv(f'{provider.id.upper()}_BASE_URL', provider.base_url).strip()})
            for provider in providers]
    except (ValidationError, ValueError):
        raise RegistryConfigError('Provider 地址必须为可信 HTTPS 端点') from None
    catalog = Catalog(providers=providers, models=models, aliases=aliases, defaults=defaults)
    for purpose, env in [('chat', 'AI_DEFAULT_MODEL'), ('agent', 'AI_AGENT_DEFAULT_MODEL')]:
        if os.getenv(env, '').strip():
            defaults[purpose] = os.environ[env].strip()
    return ModelRegistry(catalog.model_copy(update={'defaults': defaults}), dict(os.environ))


def registry_from_config(config) -> ModelRegistry:
    """Build an isolated registry from explicit Agent-owned provider settings."""
    provider_id = 'dashscope' if config.provider == 'platform' else config.provider
    spec = ProviderSpec(id=provider_id, base_url=config.base_url, api_key_env='_INJECTED_LLM_KEY')
    models = [model_definition(item, provider_id, item) for item in config.models]
    return ModelRegistry(Catalog(providers=[spec], models=models, defaults={'chat': config.model}),
                         {'_INJECTED_LLM_KEY': config.key})
