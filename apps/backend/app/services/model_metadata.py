"""Load Admin display metadata independently from the execution registry."""
import json
from pathlib import Path
from datetime import datetime, timezone

from pydantic import TypeAdapter, ValidationError

from app.core.errors import BusinessError
from app.schemas.model_metadata import ModelMetadata

METADATA_PATH = Path(__file__).resolve().parents[1] / 'data' / 'model_metadata.json'


_refreshed: dict[str, ModelMetadata] = {}

def get_model_metadata(model_id: str) -> ModelMetadata:
    if model_id in _refreshed:
        return _refreshed[model_id].model_copy(deep=True)
    try:
        entries = TypeAdapter(dict[str, ModelMetadata]).validate_python(
            json.loads(METADATA_PATH.read_text(encoding='utf-8'))
        )
    except (OSError, ValueError, ValidationError):
        raise BusinessError(10002, '模型展示资料暂不可用', 503) from None
    return entries.get(model_id, ModelMetadata())

async def refresh_model_metadata(model_id: str) -> ModelMetadata:
    from app.integrations.model_metadata import fetch_metadata

    provider, _, upstream = model_id.partition('/')
    if provider not in ('autodl', 'openlux'):
        raise BusinessError(20001, '该供应商暂未接入官网自动刷新', 422)
    previous = get_model_metadata(model_id)
    if previous.source_url is None:
        raise BusinessError(20001, '该模型尚未建立官网数据对应关系', 422)
    updates = await fetch_metadata(provider, upstream)
    candidate = previous.model_dump(mode='json')
    candidate.update(updates, verified_at=datetime.now(timezone.utc).isoformat())
    try:
        result = ModelMetadata.model_validate(candidate)
    except ValidationError:
        raise BusinessError(10002, '官网数据校验失败，已保留原资料', 503) from None
    _refreshed[model_id] = result
    return result.model_copy(deep=True)
