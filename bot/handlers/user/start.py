"""Start, menu, deep links and the subscription check."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards import user as kb
from bot.models import User
from bot.services import catalog, settings_store
from bot.utils import esc
from bot.views import show_cart, show_home, show_product

router = Router(name="start")

DEEP_LINK_PRODUCT = "p"
DEEP_LINK_CATEGORY = "c"


async def send_welcome(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    user: User,
    *,
    with_home: bool = True,
) -> None:
    template = await settings_store.get(session, "welcome_text")
    text = template.replace("{name}", esc(user.full_name or "do'stim"))
    await bot.send_message(
        chat_id,
        text,
        reply_markup=kb.main_reply_kb(settings.is_admin(user.tg_id)),
    )
    if with_home:
        await show_home(bot, chat_id, session, user)


async def handle_deep_link(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    user: User,
    payload: str,
) -> None:
    payload = (payload or "").strip()
    if payload == "cart":
        await show_cart(bot, chat_id, session, user)
        return
    if payload.startswith(DEEP_LINK_PRODUCT) and payload[1:].isdigit():
        product = await catalog.get_product(session, int(payload[1:]))
        if product is not None and product.is_active:
            await show_product(bot, chat_id, session, user, product, source="all")
            return
    if payload.startswith(DEEP_LINK_CATEGORY) and payload[1:].isdigit():
        category = await catalog.get_category(session, int(payload[1:]))
        if category is not None:
            from bot.views import show_products

            await show_products(
                bot, chat_id, session, user, source="cat", source_id=category.id
            )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    is_new_user: bool,
    bot: Bot,
) -> None:
    await state.clear()
    payload = (command.args or "").strip()

    if is_new_user and payload.startswith("ref_"):
        try:
            referrer = int(payload[4:])
        except ValueError:
            referrer = None
        if referrer and referrer != user.tg_id:
            found = await session.scalar(select(User.id).where(User.tg_id == referrer))
            if found is not None:
                user.referral_id = referrer

    await send_welcome(bot, message.chat.id, session, user)
    if payload:
        await handle_deep_link(bot, message.chat.id, session, user, payload)


@router.message(Command("menu"))
async def cmd_menu(
    message: Message, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    await state.clear()
    await show_home(bot, message.chat.id, session, user)


@router.callback_query(F.data == "menu")
async def cb_menu(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    await callback.answer()
    await state.clear()
    previous = callback.message if isinstance(callback.message, Message) else None
    await show_home(bot, callback.from_user.id, session, user, previous=previous)


@router.callback_query(F.data == "sub:check")
async def cb_subscription_check(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    await callback.answer("✅ Rahmat!")
    await state.clear()
    await send_welcome(bot, callback.from_user.id, session, user)


@router.message(Command("help"))
async def cmd_help(message: Message, session: AsyncSession, user: User, bot: Bot) -> None:
    shop = await settings_store.shop_config(session)
    data = await settings_store.load_all(session)
    text = (
        "ℹ️ <b>Yordam</b>\n\n"
        "🛍 <b>Katalog</b> — mahsulotlarni ko'rish\n"
        "🛒 <b>Savat</b> — tanlangan mahsulotlar\n"
        "📦 <b>Buyurtmalarim</b> — buyurtma tarixi\n"
        "❤️ <b>Saqlanganlar</b> — istaklar ro'yxati\n\n"
        f"🕘 Ish vaqti: {esc(data.get('work_hours', '—'))}\n"
    )
    if shop.support_username:
        text += f"☎️ Aloqa: @{esc(shop.support_username.lstrip('@'))}"
    await message.answer(text, reply_markup=kb.main_reply_kb(settings.is_admin(user.tg_id)))
