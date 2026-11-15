"""Admin / customer notifications."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.models import Order
from bot.services import users as users_service
from bot.views import order_text

log = logging.getLogger(__name__)


def _targets() -> list[int]:
    if settings.admin_log_chat_id:
        return [settings.admin_log_chat_id]
    return list(settings.admin_ids)


async def notify_admins(
    bot: Bot,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    for chat_id in _targets():
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
        except TelegramForbiddenError:
            log.warning("Admin chat %s has blocked the bot", chat_id)
        except TelegramBadRequest as exc:
            log.warning("Cannot notify admin chat %s: %s", chat_id, exc)


async def notify_user(bot: Bot, tg_id: int, text: str, **kwargs) -> bool:
    try:
        await bot.send_message(tg_id, text, **kwargs)
        return True
    except (TelegramForbiddenError, TelegramBadRequest):
        return False


async def new_order(bot: Bot, order: Order) -> None:
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚙️ Buyurtmani ochish", callback_data=f"a:order:{order.id}"
                )
            ]
        ]
    )
    await notify_admins(bot, "🆕 <b>YANGI BUYURTMA</b>\n\n" + order_text(order, admin=True), reply_markup=markup)


async def mark_blocked(session: AsyncSession, tg_id: int) -> None:
    user = await users_service.get_or_create(session, tg_id)
    user[0].is_blocked = True
