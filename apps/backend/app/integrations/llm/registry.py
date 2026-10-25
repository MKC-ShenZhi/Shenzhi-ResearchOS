"""Typed, server-only model catalog. Never serialize provider configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.core.errors import BusinessError

Purpose = Literal['chat', 'agent']


class RegistryConfigError(BusinessError):
    def __init__(self, message: str):
        super().__init__(20004, f'模型注册配置错误：{message}', 503)


class Definition(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, str_strip_whitespace=True)


class Capabilities(Definition):
    chat: bool = True
    streaming: bool = True
    tool_calling: bool = False
    reasoning: bool = False
    temperature: bool = True
    thinking: Literal['none', 'enable_thinking', 'thinking'] = 'none'
    stream_options: bool = False
    # Separate product budgets; the model's hard ceiling is applied to both.
    chat_max_tokens: int = Field(default=4096, gt=0)
    agent_max_tokens: int = Field(default=32768, gt=0)
    max_output_tokens: int = Field(default=4096, gt=0)

    def supports(self, purpose: Purpose) -> bool:
        return self.chat and self.streaming and (purpose != 'agent' or self.tool_calling)


class ProviderSpec(Definition):
    id: str = Field(min_length=1)
    protocol: Literal['openai_chat_completions'] = 'openai_chat_completions'
    base_url: str
    api_key_env: str = Field(min_length=1)
    enabled: bool = True

    @field_validator('base_url')
    @classmethod
    def trusted_endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        port = parsed.port  # Also reject malformed or out-of-range ports.
        if (port == 0 or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise ValueError('provider endpoint must be HTTPS without credentials, query or fragment')
        return value.rstrip('/')


class ModelSpec(Definition):
    id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    upstream_model: str = Field(min_length=1)
    label: str = Field(min_length=1)
    brand: str = 'platform'
    description: str = ''
    enabled: bool = True
    capabilities: Capabilities = Field(default_factory=Capabilities)
    # Only explicitly supported vendor parameters may enter a request.
    request_params: dict = Field(default_factory=dict)

    @field_validator('request_params')
    @classmethod
    def vendor_params(cls, value: dict) -> dict:
        for key, item in value.items():
            if key == 'enable_thinking' and type(item) is bool:
                continue
            if (key == 'thinking' and isinstance(item, dict) and set(item) == {'type'}
                    and item['type'] in ('enabled', 'disabled')):
                continue
            raise ValueError('unsupported model request parameter')
        return value


class Catalog(Definition):
    providers: list[ProviderSpec] = Field(default_factory=list)
    models: list[ModelSpec] = Field(default_factory=list)
    aliases: dict[str, str] = Field(default_factory=dict)
    defaults: dict[str, str] = Field(default_factory=dict)


@dataclass(frozen=True)
class ProviderConfig:
    spec: ProviderSpec
    key: SecretStr = field(repr=False)

    @property
    def configured(self) -> bool:
        return self.spec.enabled and bool(self.key.get_secret_value())


@dataclass(frozen=True)
class ResolvedModel:
    spec: ModelSpec
    provider: ProviderConfig

    @property
    def upstream_model(self) -> str:
        return self.spec.upstream_model

    @property
    def base_url(self) -> str:
        return self.provider.spec.base_url

    @property
    def key(self) -> str:
        return self.provider.key.get_secret_value()


class ModelRegistry:
    def __init__(self, catalog: Catalog, keys: dict[str, str]):
        self.providers: dict[str, ProviderConfig] = {}
        self.models: dict[str, ModelSpec] = {}
        for provider in catalog.providers:
            if provider.id in self.providers:
                raise RegistryConfigError('存在重复 Provider ID')
            self.providers[provider.id] = ProviderConfig(provider, SecretStr(keys.get(provider.api_key_env, '').strip()))
        for model in catalog.models:
            if model.id in self.models or model.id == 'default':
                raise RegistryConfigError('存在重复或保留 Model ID')
            if model.provider_id not in self.providers:
                raise RegistryConfigError('模型引用未知 Provider')
            if any(key != model.capabilities.thinking for key in model.request_params):
                raise RegistryConfigError('模型参数与 thinking 能力不一致')
            self.models[model.id] = model
        self.aliases = dict(catalog.aliases)
        if any(alias in self.models or alias == 'default' or target not in self.models
               for alias, target in self.aliases.items()):
            raise RegistryConfigError('兼容别名冲突或指向未知模型')
        self.defaults = {purpose: self.aliases.get(model_id, model_id)
                         for purpose, model_id in catalog.defaults.items()}
        if set(self.defaults) - {'chat', 'agent'}:
            raise RegistryConfigError('未知默认模型用途')
        for purpose, model_id in self.defaults.items():
            model = self.models.get(model_id)
            if not model or not model.enabled or not model.capabilities.supports(purpose):
                raise RegistryConfigError('默认模型不存在、禁用或不支持所需能力')

    def list_models(self, purpose: Purpose = 'chat') -> list[ModelSpec]:
        return [model for model in self.models.values() if model.capabilities.supports(purpose)]

    def default_model(self, purpose: Purpose = 'chat') -> ModelSpec:
        if purpose in self.defaults:
            return self.models[self.defaults[purpose]]
        shared = self.models.get(self.defaults.get('chat', ''))
        if purpose == 'agent' and shared and shared.capabilities.supports(purpose):
            return shared
        candidates = [model for model in self.list_models(purpose) if model.enabled]
        configured = [model for model in candidates if self.providers[model.provider_id].configured]
        if not candidates:
            raise BusinessError(20001, '没有支持当前业务的模型，请联系管理员', 503)
        return (configured or candidates)[0]

    def resolve_model(self, model_id: str | None, purpose: Purpose = 'chat', *,
                      require_configured: bool = True) -> ResolvedModel:
        chosen = self.default_model(purpose).id if not model_id or model_id == 'default' else model_id
        model = self.models.get(self.aliases.get(chosen, chosen))
        if model is None:
            raise BusinessError(20001, '所选模型未注册，请刷新后选择可用模型')
        if not model.enabled:
            raise BusinessError(20001, '所选模型已禁用，请选择其他模型')
        if not model.capabilities.supports(purpose):
            detail = '（Agent 需要 Tool Calling）' if purpose == 'agent' else ''
            raise BusinessError(20001, f'所选模型不支持当前业务所需能力{detail}')
        provider = self.providers[model.provider_id]
        if not provider.spec.enabled or (not provider.configured and require_configured):
            raise BusinessError(20004, '所选模型的 Provider 未启用或未配置凭据，请联系管理员', 503)
        return ResolvedModel(model, provider)

    def public_models(self, purpose: Purpose) -> list[dict]:
        result = []
        for model in self.list_models(purpose):
            provider = self.providers[model.provider_id]
            if not provider.configured:
                continue
            enabled = model.enabled and provider.configured
            result.append({
                'value': model.id, 'label': model.label, 'provider': model.brand,
                'provider_id': model.provider_id, 'brand': model.brand,
                'aliases': [alias for alias, target in self.aliases.items() if target == model.id],
                'description': model.description, 'enabled': enabled,
                **({} if enabled else {'reason': 'model_disabled' if not model.enabled else 'provider_not_configured'}),
                'capabilities': model.capabilities.model_dump(),
            })
        return result

    def public_default(self, purpose: Purpose) -> str | None:
        models = self.public_models(purpose)
        if not any(model['enabled'] for model in models):
            return None
        default = self.default_model(purpose).id
        return default if any(model['value'] == default for model in models) else None
