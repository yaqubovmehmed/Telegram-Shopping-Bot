"""Channel subscription gate (uses fresh ``chat_member`` updates + cache)."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import settings
from bot.keyboards.user import subscription_kb
from bot.services import settings_store

MEMBER_STATUSES = {"creator", "administrator", "member", "restricted"}

_guard: "SubscriptionMiddleware | None" = None


def invalidate_user(user_id: int) -> None:
    if _guard is not None:
        _guard.invalidate(user_id)


class SubscriptionMiddleware(BaseMiddleware):
    def __init__(self, bot: Bot) -> None:
        global _guard
        self.bot = bot
        self._cache: dict[int, tuple[bool, float]] = {}
        self.ttl = 300.0
        _guard = self

    def invalidate(self, user_id: int) -> None:
        self._cache.pop(user_id, None)

    async def is_member(self, user_id: int) -> bool:
        cached = self._cache.get(user_id)
        if cached and time.monotonic() - cached[1] < self.ttl:
            return cached[0]
        allowed = True
        if settings.required_channel_id:
            try:
                member = await self.bot.get_chat_member(settings.required_channel_id, user_id)
                allowed = member.status in MEMBER_STATUSES
                if member.status == "restricted":
                    allowed = bool(getattr(member, "is_member", False))
            except Exception:
                # Never lock users out because of a temporary API error.
                allowed = True
        self._cache[user_id] = (allowed, time.monotonic())
        return allowed

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not settings.required_channel_id:
            return await handler(event, data)

        tg_user = data.get("event_from_user")
        if tg_user is None or settings.is_admin(tg_user.id):
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data == "sub:check":
            self.invalidate(tg_user.id)
            if await self.is_member(tg_user.id):
                await event.answer("✅ Obuna tasdiqlandi!", show_alert=False)
                if isinstance(event.message, Message):
                    try:
                        await event.message.delete()
                    except Exception:
                        pass
                data["subscription_just_passed"] = True
                return await handler(event, data)
            await event.answer("❌ Siz hali kanalga obuna bo'lmadingiz.", show_alert=True)
            return None

        if await self.is_member(tg_user.id):
            return await handler(event, data)

        session = data.get("session")
        channel_url = settings.required_channel_url
        if session is not None:
            channel_url = await settings_store.get(session, "channel_url") or channel_url

        text = (
            "🔒 <b>Botdan foydalanish uchun kanalimizga obuna bo'ling.</b>\n\n"
            "Obuna bo'lgandan so'ng «✅ Tekshirish» tugmasini bosing."
        )
        if isinstance(event, CallbackQuery):
            await event.answer("🔒 Avval kanalga obuna bo'ling.", show_alert=True)
        if isinstance(event, Message):
            await event.answer(text, reply_markup=subscription_kb(channel_url))
        return None
