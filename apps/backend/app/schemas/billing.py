from typing import Literal
from pydantic import BaseModel, ConfigDict


class CreateOrder(BaseModel):
    model_config = ConfigDict(extra='forbid')
    plan_id: Literal['basic', 'pro', 'research']
    channel: Literal['alipay', 'wechat']
