"""Inline mode: share products anywhere, add to cart from the sent message."""

from __future__ import annotations

from aiogram import Bot, Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultsButton,
    InputTextMessageContent,
    LinkPreviewOptions,
    WebAppInfo,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.services import catalog
from bot.utils import esc, money, short

router = Router(name="inline")


@router.inline_query()
async def on_inline_query(query: InlineQuery, session: AsyncSession, bot: Bot) -> None:
    text = (query.query or "").strip()
    if text.startswith("p") and text[1:].isdigit():
        product = await catalog.get_product(session, int(text[1:]))
        products = [product] if product is not None and product.is_active else []
    else:
        products, _, _ = await catalog.products_page(
            session,
            page=1,
            per_page=20,
            search=text or None,
            active_only=True,
        )

    try:
        me = await bot.get_me()
        username = me.username or ""
    except Exception:
        username = ""

    results: list[InlineQueryResultArticle] = []
    for product in products:
        stock = (
            f"📦 {product.stock} dona"
            if product.stock > 0
            else "⛔️ Omborda qolmagan"
        )
        body = (
            f"<b>{esc(product.title)}</b>\n\n"
            f"💰 <b>{money(product.price)}</b>\n"
            f"{stock}\n"
        )
        if product.description:
            body += f"\n{esc(short(product.description, 300))}"

        buttons = []
        if product.stock > 0:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text="🛒 Savatga qo'shish", callback_data=f"add:{product.id}"
                    )
                ]
            )
        if username:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text="🤖 Botni ochish",
                        url=f"https://t.me/{username}?start=p{product.id}",
                    )
                ]
            )

        results.append(
            InlineQueryResultArticle(
                id=f"p{product.id}",
                title=product.title,
                description=f"{money(product.price)} · {stock}",
                input_message_content=InputTextMessageContent(
                    message_text=body,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None,
            )
        )

    button = None
    if settings.webapp_enabled and settings.webapp_url:
        button = InlineQueryResultsButton(
            text="🚀 Mini App'da xarid qilish",
            web_app=WebAppInfo(url=settings.webapp_url),
        )

    await query.answer(
        results,
        cache_time=5,
        is_personal=True,
        button=button,
    )
