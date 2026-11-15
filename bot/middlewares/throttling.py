"""Simple in-memory anti-flood guard."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import settings


class ThrottlingMiddleware(BaseMiddleware):
    """Allow ``limit`` events per ``window`` seconds for each user."""

    def __init__(self, limit: int | None = None, window: float | None = None) -> None:
        self.limit = limit or settings.throttle_limit
        self.window = window or settings.throttle_window
        self._hits: dict[int, list[float]] = {}

    def _blocked(self, user_id: int) -> bool:
        now = time.monotonic()
        hits = self._hits.setdefault(user_id, [])
        cutoff = now - self.window
        if hits and hits[-1] < cutoff:
            hits.clear()
        if len(hits) >= self.limit:
            return True
        hits.append(now)
        if len(self._hits) > 5000:
            self._prune(now)
        return False

    def _prune(self, now: float) -> None:
        cutoff = now - self.window * 4
        for key in [key for key, hits in self._hits.items() if not hits or hits[-1] < cutoff]:
            self._hits.pop(key, None)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or settings.is_admin(tg_user.id):
            return await handler(event, data)

        if not self._blocked(tg_user.id):
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer("⏳ Iltimos, biroz kuting.", show_alert=False)
        elif isinstance(event, Message):
            await event.answer("⏳ Iltimos, biroz kuting va qaytadan urinib ko'ring.")
        return None
