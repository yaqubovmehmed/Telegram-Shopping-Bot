"""Attach the database user record to every update."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services import users as users_service


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        session: AsyncSession | None = data.get("session")
        if tg_user is None or tg_user.is_bot or session is None:
            return await handler(event, data)

        user, is_new = await users_service.get_or_create(
            session,
            tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
        )
        changed = False
        if user.username != tg_user.username:
            user.username = tg_user.username
            changed = True
        if user.full_name != tg_user.full_name and tg_user.full_name:
            user.full_name = tg_user.full_name
            changed = True
        if changed:
            await session.flush()

        data["user"] = user
        data["is_new_user"] = is_new
        return await handler(event, data)
