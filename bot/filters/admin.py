"""Authorization filters."""

from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from bot.config import settings


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, **kwargs: Any) -> bool:
        user = kwargs.get("event_from_user")
        return bool(user and not user.is_bot and settings.is_admin(user.id))


class IsPrivate(BaseFilter):
    async def __call__(self, event: TelegramObject, **kwargs: Any) -> bool:
        chat = kwargs.get("event_chat")
        return bool(chat and chat.type == "private")
