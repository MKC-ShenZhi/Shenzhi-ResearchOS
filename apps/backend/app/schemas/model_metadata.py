"""Display-only model information for the Admin catalog."""
from pydantic import AwareDatetime, BaseModel, Field, HttpUrl, model_validator


class PriceTier(BaseModel):
    label: str
    currency: str = Field(min_length=3, max_length=3)
    input_min_tokens: int = Field(default=0, ge=0)
    input_max_tokens: int | None = Field(default=None, gt=0)
    schedule: str | None = None
    input: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    cache_read: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    cache_write: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def valid_range(self):
        if self.input_max_tokens is not None and self.input_max_tokens <= self.input_min_tokens:
            raise ValueError('Invalid input token range')
        return self


class ModelMetadata(BaseModel):
    description: str | None = None
    context_length_display: str | None = None
    notes: list[str] = Field(default_factory=list)
    documentation_url: HttpUrl | None = None
    source_url: HttpUrl | None = None
    verified_at: AwareDatetime | None = None
    effective_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None
    pricing: list[PriceTier] = Field(default_factory=list)

    @model_validator(mode='after')
    def price_source(self):
        if self.pricing and (self.source_url is None or self.verified_at is None):
            raise ValueError('Prices require a source and verification time')
        return self
