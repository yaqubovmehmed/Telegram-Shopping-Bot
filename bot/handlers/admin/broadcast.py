"""Admin: broadcast to every customer and promo code management."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.admin.common import cb_message
from bot.keyboards.admin import _btn, broadcast_confirm_kb, promos_admin_kb
from bot.models import Broadcast, User
from bot.services import promo as promo_service
from bot.services import users as users_service
from bot.states import BroadcastForm, PromoForm
from bot.utils import esc, parse_int

router = Router(name="admin-broadcast")
log = logging.getLogger(__name__)


# --- broadcast ------------------------------------------------------------


@router.callback_query(F.data == "a:bcast")
async def cb_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(BroadcastForm.content)
    message = cb_message(callback)
    if message is not None:
        await message.answer(
            "📢 <b>Xabar yuborish</b>\n\n"
            "Yubormoqchi bo'lgan xabaringizni yuboring — matn, rasm, video yoki fayl.\n"
            "Formatlash saqlanadi.\n\n"
            "Bekor qilish uchun /cancel buyrug'ini yuboring."
        )


@router.message(BroadcastForm.content)
async def broadcast_preview(
    message: Message, state: FSMContext, user: User, bot: Bot
) -> None:
    if message.text and message.text.strip().startswith("/"):
        await state.clear()
        await message.answer("❌ Bekor qilindi.")
        return

    await state.update_data(
        bc_chat=message.chat.id,
        bc_msg=message.message_id,
        bc_type=message.content_type,
    )
    await state.set_state(None)
    count = "barcha foydalanuvchilarga"
    await message.answer(f"👁 Quyida xabaringiz ko'rinishi. {count} yuboriladi.")
    await bot.copy_message(
        chat_id=message.chat.id,
        from_chat_id=message.chat.id,
        message_id=message.message_id,
        reply_markup=broadcast_confirm_kb(),
    )


@router.callback_query(F.data == "a:bcast_send")
async def cb_broadcast_send(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    data = await state.get_data()
    chat_id = data.get("bc_chat")
    message_id = data.get("bc_msg")
    if not chat_id or not message_id:
        await callback.answer(
            "Xabar topilmadi. Qaytadan yuboring.", show_alert=True
        )
        return

    await callback.answer("🚀 Yuborilmoqda…")
    user_ids = await users_service.all_ids(session)
    sent = 0
    failed = 0
    blocked: list[int] = []

    for index, tg_id in enumerate(user_ids, 1):
        try:
            await bot.copy_message(
                chat_id=tg_id,
                from_chat_id=int(chat_id),
                message_id=int(message_id),
            )
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            try:
                await bot.copy_message(
                    chat_id=tg_id,
                    from_chat_id=int(chat_id),
                    message_id=int(message_id),
                )
                sent += 1
            except Exception:
                failed += 1
        except TelegramForbiddenError:
            failed += 1
            blocked.append(tg_id)
        except TelegramBadRequest:
            failed += 1
        except Exception:
            failed += 1

        if index % 25 == 0:
            await asyncio.sleep(1.0)
        else:
            await asyncio.sleep(0.05)

    if blocked:
        await session.execute(
            update(User).where(User.tg_id.in_(blocked)).values(is_blocked=True)
        )
    session.add(Broadcast(admin_id=_admin_id(callback), sent=sent, failed=failed))
    await state.clear()

    message = cb_message(callback)
    report = (
        "📢 <b>Xabar yuborildi</b>\n\n"
        f"✅ Yetkazildi: <b>{sent}</b>\n"
        f"❌ Xatolik: <b>{failed}</b>\n"
        f"🚫 Botni bloklagan: <b>{len(blocked)}</b>"
    )
    if message is not None:
        await message.answer(report)


def _admin_id(callback: CallbackQuery) -> int:
    return callback.from_user.id if callback.from_user else 0


# --- promo codes ----------------------------------------------------------


async def _render_promos(target: Message, session: AsyncSession, *, edit: bool = False) -> None:
    promos = await promo_service.list_all(session)
    text = "🎟 <b>Promokodlar</b>\n\n"
    if promos:
        text += "\n".join(promo_service.describe(promo) for promo in promos)
        text += "\n\nHolatni almashtirish uchun kodni, o'chirish uchun 🗑 ni bosing."
    else:
        text += "Hozircha promokodlar yo'q. ➕ tugmasi bilan qo'shing."
    markup = promos_admin_kb(promos)
    if edit:
        try:
            await target.edit_text(text, reply_markup=markup)
            return
        except Exception:
            pass
    await target.answer(text, reply_markup=markup)


@router.callback_query(F.data == "a:promos")
async def cb_promos(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    message = cb_message(callback)
    if message is not None:
        await _render_promos(message, session, edit=True)


@router.callback_query(F.data == "a:pnewpromo")
async def cb_new_promo(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(PromoForm.code)
    message = cb_message(callback)
    if message is not None:
        await message.answer(
            "🎟 <b>Yangi promokod</b>\n\n"
            "1/5 — Kodni yozing (3–32 belgi, harf/raqam). Masalan: <code>YANGIYIL</code>"
        )


@router.message(PromoForm.code, F.text)
async def promo_code(message: Message, state: FSMContext, session: AsyncSession) -> None:
    code = (message.text or "").strip().upper()
    if not 3 <= len(code) <= 32 or not code.replace("-", "").replace("_", "").isalnum():
        await message.answer("❗️ Kod 3–32 belgi, faqat harf, raqam, - va _ bo'lsin.")
        return
    if await promo_service.get_by_code(session, code):
        await message.answer("❗️ Bu kod allaqachon mavjud. Boshqa kod yozing.")
        return

    await state.update_data(promo_code=code)
    await state.set_state(PromoForm.value)
    await message.answer(
        f"2/5 — <b>{esc(code)}</b> uchun chegirma turini tanlang:",
        reply_markup=promo_kind_kb(),
    )


def promo_kind_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("📉 Foiz (%)", "a:pkind:percent"),
                _btn("💵 Summa (so'm)", "a:pkind:fixed"),
            ]
        ]
    )


@router.callback_query(F.data.startswith("a:pkind:"))
async def promo_kind(
    callback: CallbackQuery, state: FSMContext
) -> None:
    kind = (callback.data or "").split(":")[2]
    if kind not in {"percent", "fixed"}:
        await callback.answer()
        return
    await callback.answer()
    await state.update_data(promo_kind=kind)
    await state.set_state(PromoForm.value)
    message = cb_message(callback)
    if message is not None:
        hint = "foizni (1–90)" if kind == "percent" else "chegirma summasini (so'mda)"
        await message.answer(f"3/5 — {hint} yozing:")


@router.message(PromoForm.value, F.text)
async def promo_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    kind = data.get("promo_kind", "percent")
    value = parse_int(message.text or "", minimum=1, maximum=10_000_000_000)
    if value is None:
        await message.answer("❗️ Butun son kiriting.")
        return
    if kind == "percent" and value > 90:
        await message.answer("❗️ Foiz 1–90 oralig'ida bo'lsin.")
        return

    await state.update_data(promo_value=value)
    await state.set_state(PromoForm.min_total)
    await message.answer(
        "4/5 — Minimal buyurtma summasi (so'm). Cheklov yo'q bo'lsa <code>0</code> yozing:"
    )


@router.message(PromoForm.min_total, F.text)
async def promo_min_total(message: Message, state: FSMContext) -> None:
    value = parse_int(message.text or "", minimum=0, maximum=10_000_000_000)
    if value is None:
        await message.answer("❗️ Butun son kiriting (0 ham bo'ladi).")
        return
    await state.update_data(promo_min=value)
    await state.set_state(PromoForm.max_uses)
    await message.answer(
        "5/5 — Nechta buyurtmada ishlatilishi mumkin? Cheklov yo'q bo'lsa <code>0</code>:"
    )


@router.message(PromoForm.max_uses, F.text)
async def promo_max_uses(message: Message, state: FSMContext) -> None:
    value = parse_int(message.text or "", minimum=0, maximum=1_000_000)
    if value is None:
        await message.answer("❗️ Butun son kiriting (0 ham bo'ladi).")
        return
    await state.update_data(promo_max=value)
    await state.set_state(PromoForm.days)
    await message.answer(
        "⏳ Necha kun amal qiladi? Muddat yo'q bo'lsa <code>0</code>:"
    )


@router.message(PromoForm.days, F.text)
async def promo_days(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    value = parse_int(message.text or "", minimum=0, maximum=3650)
    if value is None:
        await message.answer("❗️ Kunlar sonini butun sonda kiriting (0 ham bo'ladi).")
        return

    data = await state.get_data()
    promo, error = await promo_service.create(
        session,
        code=data.get("promo_code", ""),
        kind=data.get("promo_kind", "percent"),
        value=int(data.get("promo_value", 0)),
        min_total=int(data.get("promo_min", 0)),
        max_uses=int(data.get("promo_max", 0)) or None,
        days=value or None,
    )
    await state.clear()
    if error or promo is None:
        await message.answer(f"❌ {error or 'Xatolik yuz berdi.'}")
        return

    await message.answer(
        f"✅ Promokod yaratildi:\n\n{promo_service.describe(promo)}",
        reply_markup=promos_admin_kb(await promo_service.list_all(session)),
    )


@router.callback_query(F.data.startswith("a:ptogpromo:"))
async def cb_toggle_promo(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    try:
        promo_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    promo = await promo_service.get(session, promo_id)
    if promo is None:
        await callback.answer("Promokod topilmadi.", show_alert=True)
        return
    await promo_service.deactivate(session, promo)
    await callback.answer("🟢 Faol" if promo.is_active else "⚪️ Nofaol")
    message = cb_message(callback)
    if message is not None:
        await _render_promos(message, session, edit=True)


@router.callback_query(F.data.startswith("a:pdelpromo:"))
async def cb_delete_promo(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    try:
        promo_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    promo = await promo_service.get(session, promo_id)
    if promo is None:
        await callback.answer("Promokod topilmadi.", show_alert=True)
        return
    await session.delete(promo)
    await session.flush()
    await callback.answer("🗑 O'chirildi")
    message = cb_message(callback)
    if message is not None:
        await _render_promos(message, session, edit=True)
