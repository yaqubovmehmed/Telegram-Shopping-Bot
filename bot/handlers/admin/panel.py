"""Admin panel home, statistics and shop settings."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.admin import ADMIN_BTN, panel_kb, settings_kb
from bot.models import User
from bot.services import orders as orders_service
from bot.services import settings_store
from bot.states import ShopSettingForm
from bot.utils import esc, money, status_label

router = Router(name="admin-panel")


def panel_text(stats: orders_service.ShopStats) -> str:
    lines = [
        "🛠 <b>Admin panel</b>",
        "",
        f"👥 Foydalanuvchilar: <b>{stats.users_total}</b> "
        f"(bugun +{stats.users_today})",
        f"📦 Buyurtmalar: <b>{stats.orders_total}</b> (bugun {stats.orders_today})",
        f"🕒 Faol buyurtmalar: <b>{stats.active_orders}</b>",
        f"💰 Yetkazilganlar tushumi: <b>{money(stats.revenue)}</b>",
        "",
        "Kerakli bo'limni tanlang 👇",
    ]
    return "\n".join(lines)


def stats_text(stats: orders_service.ShopStats) -> str:
    lines = [
        "📊 <b>Statistika</b>",
        "",
        f"👥 Foydalanuvchilar: <b>{stats.users_total}</b> (bugun +{stats.users_today})",
        f"📦 Jami buyurtma: <b>{stats.orders_total}</b>",
        f"🗓 Bugungi buyurtma: <b>{stats.orders_today}</b>",
        f"🕒 Faol: <b>{stats.active_orders}</b> · "
        f"📬 Yetkazilgan: <b>{stats.delivered_orders}</b> · "
        f"❌ Bekor: <b>{stats.cancelled_orders}</b>",
        "",
        f"💰 Tushum (yetkazilgan): <b>{money(stats.revenue)}</b>",
        f"⭐️ Online to'langan: <b>{money(stats.paid_online)}</b>",
        f"🧮 O'rtacha chek: <b>{money(stats.avg_check)}</b>",
        "",
        "<b>Holatlar bo'yicha:</b>",
    ]
    for status, count in stats.status_counts.items():
        lines.append(f"• {status_label(status)}: {count}")

    if stats.top_products:
        lines.append("\n<b>🔥 Eng ko'p sotilganlar:</b>")
        for index, (title, sold) in enumerate(stats.top_products, 1):
            lines.append(f"{index}. {esc(title)} — {sold} dona")
    return "\n".join(lines)


@router.message(Command("admin"))
@router.message(F.text == ADMIN_BTN)
async def admin_panel(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.clear()
    stats = await orders_service.shop_stats(session)
    await message.answer(panel_text(stats), reply_markup=panel_kb(stats.active_orders))


@router.callback_query(F.data == "a:home")
async def cb_admin_panel(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await callback.answer()
    await state.clear()
    stats = await orders_service.shop_stats(session)
    message = callback.message if isinstance(callback.message, Message) else None
    if message is not None:
        try:
            await message.edit_text(panel_text(stats), reply_markup=panel_kb(stats.active_orders))
            return
        except Exception:
            pass
        await message.answer(panel_text(stats), reply_markup=panel_kb(stats.active_orders))


@router.callback_query(F.data == "a:stats")
async def cb_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    stats = await orders_service.shop_stats(session)
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(
                stats_text(stats), reply_markup=panel_kb(stats.active_orders)
            )
        except Exception:
            pass


@router.callback_query(F.data == "a:noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


# --- settings -------------------------------------------------------------


async def _render_settings(
    target: Message, session: AsyncSession, *, edit: bool = False
) -> None:
    data = await settings_store.load_all(session)
    text = (
        "⚙️ <b>Do'kon sozlamalari</b>\n\n"
        "O'zgartirmoqchi bo'lgan maydonni tanlang. "
        "Har bir o'zgarish darhol kuchga kiradi."
    )
    markup = settings_kb(data)
    if edit:
        try:
            await target.edit_text(text, reply_markup=markup)
            return
        except Exception:
            pass
    await target.answer(text, reply_markup=markup)


@router.callback_query(F.data == "a:settings")
async def cb_settings(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await _render_settings(callback.message, session)


@router.callback_query(F.data.startswith("a:set:"))
async def cb_setting_edit(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    key = (callback.data or "").split(":", 2)[2]
    field = settings_store.FIELD_BY_KEY.get(key)
    if field is None:
        await callback.answer("Sozlama topilmadi.", show_alert=True)
        return

    data = await settings_store.load_all(session)
    current = data.get(key, "")
    await callback.answer()
    await state.set_state(ShopSettingForm.value)
    await state.update_data(setting_key=key)
    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"⚙️ <b>{field.label}</b>\n\n"
            f"Joriy qiymat: <code>{esc(current) or '—'}</code>\n\n"
            "Yangi qiymatni yuboring.",
            reply_markup=None,
        )


@router.message(ShopSettingForm.value, F.text)
async def setting_save(
    message: Message, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    data = await state.get_data()
    key = data.get("setting_key")
    field = settings_store.FIELD_BY_KEY.get(key or "")
    if field is None:
        await state.clear()
        return

    value = (message.text or "").strip()
    if field.kind == "int":
        from bot.utils import parse_int

        parsed = parse_int(value, minimum=0, maximum=10_000_000_000)
        if parsed is None:
            await message.answer("❗️ Butun son kiriting (masalan: 20000).")
            return
        value = str(parsed)
    elif field.kind == "username":
        value = value.lstrip("@")
        if value and not value.replace("_", "").isalnum():
            await message.answer("❗️ Username faqat harf, raqam va _ dan iborat bo'lsin.")
            return
    else:
        if not value or len(value) > 2000:
            await message.answer("❗️ Qiymat 1–2000 belgi oralig'ida bo'lsin.")
            return

    await settings_store.set_value(session, key, value)
    await state.clear()
    await message.answer(f"✅ Saqlandi: <b>{field.label}</b>")
    await _render_settings(message, session)
