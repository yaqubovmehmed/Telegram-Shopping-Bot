"""Data sent from the Telegram Mini App via ``sendData``."""

from __future__ import annotations

import json
import logging

from aiogram import Bot, F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import user as kb
from bot.models import User
from bot.services import cart as cart_service
from bot.views import show_cart

router = Router(name="webapp")
log = logging.getLogger(__name__)


@router.message(F.web_app_data)
async def on_web_app_data(
    message: Message, session: AsyncSession, user: User, bot: Bot
) -> None:
    raw = message.web_app_data.data if message.web_app_data else ""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        await message.answer("Mini App ma'lumotini o'qib bo'lmadi.")
        return

    items = payload.get("items")
    if not isinstance(items, list) or not items:
        await message.answer("Mini App'dan mahsulot tanlanmadi.")
        return

    added = 0
    for entry in items[:20]:
        if not isinstance(entry, dict):
            continue
        try:
            product_id = int(entry.get("id"))
            quantity = max(1, min(99, int(entry.get("qty", 1))))
        except (TypeError, ValueError):
            continue
        count, _ = await cart_service.add(session, user.id, product_id, quantity)
        added += count

    if not added:
        await message.answer("Mahsulotlarni savatga qo'shib bo'lmadi.")
        return

    await message.answer(
        f"✅ <b>{added} dona mahsulot savatga qo'shildi.</b>",
        reply_markup=kb.main_reply_kb(),
    )
    await show_cart(bot, message.chat.id, session, user)
