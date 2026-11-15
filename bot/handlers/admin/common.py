"""Tiny helpers for admin callbacks."""

from __future__ import annotations

from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


async def edit_or_send(
    callback: CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    *,
    alert: str | None = None,
    show_alert: bool = False,
) -> None:
    await callback.answer(alert or "", show_alert=show_alert)
    message = callback.message if isinstance(callback.message, Message) else None
    if message is None:
        return
    try:
        await message.edit_text(text, reply_markup=markup)
        return
    except Exception:
        pass
    try:
        await message.answer(text, reply_markup=markup)
    except Exception:
        pass


def cb_message(callback: CallbackQuery) -> Message | None:
    return callback.message if isinstance(callback.message, Message) else None
