"""Agent-owned model configuration value objects."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelConfig:
    """Explicit provider settings for local CLI and offline adapter tests."""
    key: str = field(repr=False)
    base_url: str
    model: str
    models: tuple[str, ...]
    provider: str
