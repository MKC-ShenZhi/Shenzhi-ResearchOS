"""Load Admin display metadata independently from the execution registry."""
import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from app.core.errors import BusinessError
from app.schemas.model_metadata import ModelMetadata

METADATA_PATH = Path(__file__).resolve().parents[1] / 'data' / 'model_metadata.json'


def get_model_metadata(model_id: str) -> ModelMetadata:
    try:
        entries = TypeAdapter(dict[str, ModelMetadata]).validate_python(
            json.loads(METADATA_PATH.read_text(encoding='utf-8'))
        )
    except (OSError, ValueError, ValidationError):
        raise BusinessError(10002, '模型展示资料暂不可用', 503) from None
    return entries.get(model_id, ModelMetadata())
