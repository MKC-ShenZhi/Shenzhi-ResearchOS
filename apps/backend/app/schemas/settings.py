"""Request and response contracts for personal settings."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Locale = Literal['zh-CN', 'en']
ThemeMode = Literal['light', 'dark', 'system']


class NotificationPreferences(BaseModel):
    activity: bool = True
    subscription: bool = True
    interaction: bool = True
    system: bool = True


class UserSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    locale: Locale
    theme_mode: ThemeMode
    notifications: NotificationPreferences
    created_at: datetime
    updated_at: datetime


class UserSettingsPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')

    locale: Locale | None = None
    theme_mode: ThemeMode | None = None
    notifications: NotificationPreferences | None = None
