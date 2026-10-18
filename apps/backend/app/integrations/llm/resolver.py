"""Load declarative definitions + legacy environment settings into one registry."""
from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from app.integrations.llm.registry import (
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
    builtins = _read_catalog(CATALOG_PATH)
    providers = [provider.model_copy(update={
        'base_url': os.getenv(f'{provider.id.upper()}_BASE_URL', provider.base_url).strip().rstrip('/'),
    }) for provider in builtins.providers]
    # Revalidate environment URLs too; model_copy deliberately skips validation.
    try:
        providers = [ProviderSpec.model_validate(provider.model_dump()) for provider in providers]
    except ValidationError:
        raise RegistryConfigError('Provider 地址必须为可信 HTTPS 端点') from None
    legacy = 'dashscope' if os.getenv('DASHSCOPE_API_KEY', '').strip() else 'deepseek'
    default_names = {'dashscope': 'qwen-plus', 'deepseek': 'deepseek-chat', 'zhipu': ''}
    names = {provider: os.getenv(f'{provider.upper()}_MODEL', default).strip()
             for provider, default in default_names.items()}
    models: list[ModelSpec] = []
    # Legacy provider first preserves old raw IDs. Colliding upstream IDs on another
    # provider get qualified IDs; explicit declarations can choose any stable ID.
    for provider in dict.fromkeys([legacy, 'dashscope', 'deepseek', 'zhipu']):
        upstreams = [names[provider]]
        if provider == legacy:
            upstreams += [item.strip() for item in os.getenv('AI_ALLOWED_MODELS', '').split(',')]
        for upstream in dict.fromkeys(filter(None, upstreams)):
            model_id = upstream if not any(item.id == upstream for item in models) else f'{provider}/{upstream}'
            models.append(model_definition(model_id, provider, upstream))
    aliases: dict[str, str] = {}
    defaults: dict[str, str] = {}
    path = os.getenv('AI_MODEL_REGISTRY_FILE', '').strip()
    if path:
        custom = _read_catalog(Path(path))
        # A custom definition intentionally replaces a generated legacy entry.
        # Duplicate IDs *inside* the file remain errors.
        if len({item.id for item in custom.models}) != len(custom.models):
            raise RegistryConfigError('声明文件存在重复 Model ID')
        if len({item.id for item in custom.providers}) != len(custom.providers):
            raise RegistryConfigError('声明文件存在重复 Provider ID')
        providers = [item for item in providers if item.id not in {p.id for p in custom.providers}] + custom.providers
        models = [item for item in models if item.id not in {m.id for m in custom.models}] + custom.models
        aliases, defaults = custom.aliases, dict(custom.defaults)
    # Explicit defaults take precedence over file defaults and legacy order.
    for purpose, env in [('chat', 'AI_DEFAULT_MODEL'), ('agent', 'AI_AGENT_DEFAULT_MODEL')]:
        if os.getenv(env, '').strip():
            defaults[purpose] = os.environ[env].strip()
    # With only legacy settings, DashScope wins if it has a key; otherwise DeepSeek.
    # With Zhipu alone configured, the ordinary configured-first default applies.
    if ('chat' not in defaults and (os.getenv('DASHSCOPE_API_KEY', '').strip()
                                   or os.getenv('DEEPSEEK_API_KEY', '').strip()
                                   or not os.getenv('ZHIPU_API_KEY', '').strip())):
        defaults['chat'] = names[legacy]
    return ModelRegistry(Catalog(providers=providers, models=models, aliases=aliases, defaults=defaults), dict(os.environ))


def registry_from_legacy(config) -> ModelRegistry:
    """Compatibility for existing server-side ModelConfig/MockTransport injection."""
    provider_id = 'dashscope' if config.provider == 'platform' else config.provider
    spec = ProviderSpec(id=provider_id, base_url=config.base_url, api_key_env='_INJECTED_LLM_KEY')
    models = [model_definition(item, provider_id, item) for item in config.models]
    return ModelRegistry(Catalog(providers=[spec], models=models, defaults={'chat': config.model}),
                         {'_INJECTED_LLM_KEY': config.key})
