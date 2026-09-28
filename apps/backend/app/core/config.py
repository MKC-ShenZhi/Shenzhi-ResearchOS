"""Server-only provider settings. Keys never appear in the public config."""
import math
import os
from dataclasses import dataclass
from urllib.parse import urlsplit


DEFAULT_OPENREVIEW_API_BASE_URL = 'https://api2.openreview.net'


@dataclass(frozen=True)
class ModelConfig:
    key: str
    base_url: str
    model: str
    models: tuple[str, ...]
    provider: str


@dataclass(frozen=True)
class PaperResourceConfig:
    timeout_seconds: float
    max_size_bytes: int
    openreview_api_base_url: str
    openreview_username: str
    openreview_password: str


def model_config() -> ModelConfig:
    dashscope = bool(os.getenv('DASHSCOPE_API_KEY', '').strip())
    prefix = 'DASHSCOPE' if dashscope else 'DEEPSEEK'
    default_url = ('https://dashscope.aliyuncs.com/compatible-mode/v1'
                   if dashscope else 'https://api.deepseek.com/v1')
    model = os.getenv(f'{prefix}_MODEL', 'qwen-plus' if dashscope else 'deepseek-chat').strip()
    models = tuple(dict.fromkeys([model, *filter(None, (
        item.strip() for item in os.getenv('AI_ALLOWED_MODELS', '').split(',')
    ))]))
    return ModelConfig(os.getenv(f'{prefix}_API_KEY', '').strip(),
                       os.getenv(f'{prefix}_BASE_URL', default_url).rstrip('/'),
                       model, models, 'platform' if dashscope else 'deepseek')


def _positive_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) and value > 0 else default


def normalize_openreview_api_base_url(value: str) -> str:
    """Return a trusted OpenReview HTTPS origin or the safe default."""
    try:
        candidate = value.strip()
        parsed = urlsplit(candidate)
        hostname = (parsed.hostname or '').lower()
        port = parsed.port
    except (AttributeError, TypeError, ValueError):
        return DEFAULT_OPENREVIEW_API_BASE_URL

    trusted_hostname = (
        hostname == 'openreview.net'
        or hostname.endswith('.openreview.net')
    )
    if (
        parsed.scheme.lower() != 'https'
        or not trusted_hostname
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ('', '/')
        or parsed.query
        or parsed.fragment
    ):
        return DEFAULT_OPENREVIEW_API_BASE_URL
    return f'https://{hostname}'


def paper_resource_config() -> PaperResourceConfig:
    timeout = _positive_float('PAPER_RESOURCE_TIMEOUT', 30.0)
    max_size_mb = _positive_float('PAPER_MAX_SIZE_MB', 150.0)
    openreview_api_base_url = normalize_openreview_api_base_url(
        os.getenv(
            'OPENREVIEW_API_BASE_URL',
            DEFAULT_OPENREVIEW_API_BASE_URL,
        )
    )
    return PaperResourceConfig(
        timeout_seconds=timeout,
        max_size_bytes=int(max_size_mb * 1024 * 1024),
        openreview_api_base_url=openreview_api_base_url,
        openreview_username=os.getenv('OPENREVIEW_USERNAME', '').strip(),
        openreview_password=os.getenv('OPENREVIEW_PASSWORD', ''),
    )


MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_FILE_CHARS = 30_000
MAX_ATTACHMENT_CHARS = 60_000
MAX_HISTORY_CHARS = 60_000
MAX_FILES = 5
UPLOAD_ACCEPT = ['.pdf', '.txt', '.md', '.markdown']
