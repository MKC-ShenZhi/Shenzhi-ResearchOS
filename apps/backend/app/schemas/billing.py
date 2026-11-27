from typing import Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ExpectedQuote(BaseModel):
    model_config = ConfigDict(extra='forbid')
    quoted_at: datetime
    quote_token: str


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    plan_id: Literal['research']


class CreateOrder(BaseModel):
    model_config = ConfigDict(extra='forbid')
    plan_id: Literal['basic', 'pro', 'research']
    channel: Literal['alipay', 'wechat']
    expected_quote: ExpectedQuote | None = None
