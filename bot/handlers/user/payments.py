"""Telegram Stars payments (Bot API 7.4+ / XTR currency)."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Order, User
from bot.services import notify
from bot.services import orders as orders_service
from bot.utils import money, stars_amount
from bot.views import order_text

router = Router(name="payments")
log = logging.getLogger(__name__)

CURRENCY = "XTR"  # Telegram Stars


async def send_order_invoice(bot: Bot, chat_id: int, order: Order) -> bool:
    stars = stars_amount(order.total)
    try:
        await bot.send_invoice(
            chat_id=chat_id,
            title=f"Buyurtma #{order.code}"[:32],
            description=(
                f"{len(order.items)} ta mahsulot · {money(order.total)} "
                f"= {stars} ⭐️"
            )[:255],
            payload=f"order:{order.id}",
            provider_token="",
            currency=CURRENCY,
            prices=[LabeledPrice(label=f"Buyurtma #{order.code}", amount=stars)],
        )
        return True
    except Exception:
        log.exception("Failed to create Stars invoice for order %s", order.id)
        return False


@router.callback_query(F.data.startswith("paystars:"))
async def cb_pay_with_stars(
    callback: CallbackQuery, session: AsyncSession, user: User, bot: Bot
) -> None:
    try:
        order_id = int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer()
        return
    order = await orders_service.get_order(session, order_id)
    if order is None or order.user_id != user.id:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return
    if order.payment_status == "paid":
        await callback.answer("Bu buyurtma allaqachon to'langan.", show_alert=True)
        return
    await callback.answer()
    sent = await send_order_invoice(bot, callback.from_user.id, order)
    if not sent:
        await callback.answer("Hisob-faktura yaratishda xatolik. Keyinroq urinib ko'ring.", show_alert=True)


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, session: AsyncSession, bot: Bot) -> None:
    payload = query.invoice_payload or ""
    if not payload.startswith("order:"):
        await query.answer(ok=False, error_message="Buyurtma aniqlanmadi.")
        return
    try:
        order_id = int(payload.split(":", 1)[1])
    except ValueError:
        await query.answer(ok=False, error_message="Buyurtma aniqlanmadi.")
        return

    order = await orders_service.get_order(session, order_id)
    buyer = await session.scalar(select(User).where(User.tg_id == query.from_user.id))
    if order is None or buyer is None or order.user_id != buyer.id:
        await query.answer(ok=False, error_message="Buyurtma sizga tegishli emas.")
        return
    if order.payment_status == "paid":
        await query.answer(ok=False, error_message="Buyurtma allaqachon to'langan.")
        return
    if query.currency != CURRENCY:
        await query.answer(ok=False, error_message="Valyuta noto'g'ri.")
        return
    if query.total_amount != stars_amount(order.total):
        await query.answer(ok=False, error_message="Summa o'zgargan. Qaytadan urinib ko'ring.")
        return

    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(
    message: Message, session: AsyncSession, user: User, bot: Bot
) -> None:
    payment = message.successful_payment
    if payment is None:
        return
    payload = payment.invoice_payload or ""
    if not payload.startswith("order:"):
        return
    try:
        order_id = int(payload.split(":", 1)[1])
    except ValueError:
        return

    order = await orders_service.get_order(session, order_id)
    if order is None or order.user_id != user.id:
        return
    if order.payment_status == "paid":
        await message.answer("✅ Bu buyurtma allaqachon to'langan. Rahmat!")
        return

    await orders_service.mark_paid(session, order, payment.telegram_payment_charge_id)
    log.info("Stars payment received for order %s (%s)", order.code, payment.total_amount)

    await message.answer(
        f"✅ <b>To'lov qabul qilindi!</b>\n\n"
        f"🧾 Buyurtma: <b>#{order.code}</b>\n"
        f"⭐️ To'langan: <b>{payment.total_amount} Stars</b>\n"
        f"💰 Summa: <b>{money(order.total)}</b>\n\n"
        "Operator buyurtmani tasdiqlash uchun tez orada bog'lanadi. Rahmat! 🙏"
    )
    await notify.notify_admins(
        bot, "💰 <b>TO'LOV QABUL QILINDI</b>\n\n" + order_text(order, admin=True)
    )
