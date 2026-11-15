"""Profile, support chat and global cancel/menu shortcuts."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards import user as kb
from bot.models import Order, User
from bot.services import favorites as fav_service, settings_store
from bot.states import Support
from bot.utils import esc, fmt_dt
from bot.views import show_home

router = Router(name="profile")


@router.message(F.text == kb.BTN_MAIN_MENU)
@router.message(Command("cancel"))
async def go_home(
    message: Message, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    await state.clear()
    await show_home(bot, message.chat.id, session, user)


@router.message(F.text == kb.BTN_CANCEL)
async def cancel_button(
    message: Message, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    data = await state.get_data()
    await state.clear()
    if data.get("items"):
        await message.answer("❌ Buyurtma rasmiylashtirish bekor qilindi.")
    elif data.get("receipt_order"):
        await message.answer("❌ Chek yuborish bekor qilindi.")
    await show_home(bot, message.chat.id, session, user)


async def profile_text(session: AsyncSession, user: User, bot: Bot) -> str:
    orders_count = int(
        await session.scalar(
            select(func.count(Order.id)).where(Order.user_id == user.id)
        )
        or 0
    )
    favorites_count = await fav_service.count(session, user.id)
    try:
        me = await bot.get_me()
        ref_link = f"https://t.me/{me.username}?start=ref_{user.tg_id}"
    except Exception:
        ref_link = "—"

    lines = [
        "👤 <b>Profil</b>",
        "",
        f"🙋‍♂️ Ism: <b>{esc(user.full_name)}</b>",
        f"🆔 ID: <code>{user.tg_id}</code>",
    ]
    if user.username:
        lines.append(f"🔗 Username: @{esc(user.username)}")
    lines.append(f"📞 Telefon: {esc(user.phone) if user.phone else '—'}")
    lines.append(f"📅 Ro'yxatdan o'tgan: {fmt_dt(user.created_at, '%d.%m.%Y')}")
    lines.append("")
    lines.append(f"📦 Buyurtmalar: <b>{orders_count}</b> ta")
    lines.append(f"❤️ Saqlanganlar: <b>{favorites_count}</b> ta")
    lines.append("")
    lines.append("🎁 Do'stlaringizni taklif qiling:")
    lines.append(f"<code>{esc(ref_link)}</code>")
    return "\n".join(lines)


@router.message(F.text == kb.BTN_PROFILE)
async def profile_button(
    message: Message, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    await state.clear()
    await message.answer(
        await profile_text(session, user, bot), reply_markup=kb.profile_kb()
    )


@router.callback_query(F.data == "profile")
async def cb_profile(
    callback: CallbackQuery, session: AsyncSession, user: User, bot: Bot
) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            await profile_text(session, user, bot), reply_markup=kb.profile_kb()
        )


# --- support --------------------------------------------------------------


async def support_message(session: AsyncSession) -> str:
    shop = await settings_store.shop_config(session)
    data = await settings_store.load_all(session)
    text = (
        "☎️ <b>Yordam xizmati</b>\n\n"
        "Savollaringiz, takliflaringiz yoki shikoyatlaringiz bo'lsa, "
        "bizga yozing — tez orada javob beramiz.\n\n"
        f"🕘 Ish vaqti: {esc(data.get('work_hours', '—'))}\n"
    )
    if shop.support_username:
        text += f"💬 Telegram: @{esc(shop.support_username.lstrip('@'))}\n"
    text += "\n✍️ «Xabar qoldirish» tugmasi orqali to'g'ridan-to'g'ri yozishingiz mumkin."
    return text


@router.message(F.text == kb.BTN_SUPPORT)
async def support_button(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    await state.clear()
    shop = await settings_store.shop_config(session)
    await message.answer(
        await support_message(session), reply_markup=kb.support_kb(shop.support_username)
    )


@router.callback_query(F.data == "support")
async def cb_support(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User
) -> None:
    await state.clear()
    await callback.answer()
    shop = await settings_store.shop_config(session)
    text = await support_message(session)
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(
                text, reply_markup=kb.support_kb(shop.support_username)
            )
        except Exception:
            await callback.message.answer(
                text, reply_markup=kb.support_kb(shop.support_username)
            )


@router.callback_query(F.data == "support:msg")
async def cb_support_message(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Support.message)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "✍️ Xabaringizni yozing yoki rasm/fayl yuboring.\n"
            "Bekor qilish uchun «❌ Bekor qilish» tugmasini bosing.",
            reply_markup=kb.cancel_reply_kb(),
        )


@router.message(Support.message)
async def support_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    text = (message.text or message.caption or "").strip()
    if len(text) > 2000:
        await message.answer("❗️ Xabar juda uzun (maksimum 2000 belgi).")
        return

    await state.clear()
    admin_chat = settings.admin_log_chat_id or (settings.admin_ids[0] if settings.admin_ids else None)
    if admin_chat is not None:
        header = (
            f"📩 <b>Murojaat</b>\n\n"
            f"👤 {esc(user.full_name)} · <code>{user.tg_id}</code>"
            + (f" · @{esc(user.username)}" if user.username else "")
        )
        if text:
            header += f"\n\n💬 {esc(text)}"
        try:
            await bot.send_message(admin_chat, header)
            if message.text is None:
                await bot.copy_message(admin_chat, message.chat.id, message.message_id)
        except Exception:
            pass

    await message.answer(
        "✅ Xabaringiz adminga yuborildi. Tez orada javob beramiz!",
        reply_markup=kb.main_reply_kb(settings.is_admin(user.tg_id)),
    )


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()
