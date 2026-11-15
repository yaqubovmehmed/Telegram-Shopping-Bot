"""Admin: order queue and statuses."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.admin.common import edit_or_send
from bot.keyboards.admin import FILTERS, order_admin_kb, orders_list_kb
from bot.models import Order
from bot.services import notify
from bot.services import orders as orders_service
from bot.utils import esc, fmt_dt, money, status_label
from bot.views import order_text

router = Router(name="admin-orders")
log = logging.getLogger(__name__)


async def _status_counts(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(select(Order.status, func.count(Order.id)).group_by(Order.status))
    ).all()
    return {status: count for status, count in rows}


@router.callback_query(F.data.startswith("a:orders:"))
async def cb_orders(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = (callback.data or "").split(":")
    status = parts[2] if len(parts) > 2 else "all"
    try:
        page = int(parts[3]) if len(parts) > 3 else 1
    except ValueError:
        page = 1
    if status not in {key for key, _ in FILTERS}:
        status = "all"

    orders, total, total_pages = await orders_service.admin_orders(
        session, status=status if status != "all" else None, page=page
    )
    counts = await _status_counts(session)

    title = "🗂 Barcha buyurtmalar" if status == "all" else status_label(status)
    lines = [f"📦 <b>{title}</b>", f"Jami: {total} ta · {page}/{total_pages}", ""]
    for order in orders:
        lines.append(
            f"<b>#{order.code}</b> · {order.total:,} so'm".replace(",", " ")
            + f" · {status_label(order.status)}\n"
            f"👤 {esc(order.contact_name)} · {fmt_dt(order.created_at, '%d.%m %H:%M')}"
        )
    if not orders:
        lines.append("Bu bo'limda buyurtmalar yo'q.")

    await edit_or_send(
        callback,
        "\n".join(lines),
        orders_list_kb(orders, status, page, total_pages, counts),
    )


@router.callback_query(F.data.startswith("a:order:"))
async def cb_order_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        order_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    order = await orders_service.get_order(session, order_id)
    if order is None:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return
    await edit_or_send(callback, order_text(order, admin=True), order_admin_kb(order))


@router.callback_query(F.data.startswith("a:ost:"))
async def cb_change_status(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer()
        return
    try:
        order_id = int(parts[2])
    except ValueError:
        await callback.answer()
        return
    new_status = parts[3]

    order = await orders_service.get_order(session, order_id)
    if order is None:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return

    error = await orders_service.set_status(session, order, new_status)
    if error:
        await callback.answer(error, show_alert=True)
        return

    await callback.answer(f"✅ {status_label(new_status)}")
    await _notify_customer(bot, order, new_status)
    await edit_or_send(callback, order_text(order, admin=True), order_admin_kb(order))


async def _notify_customer(bot: Bot, order: Order, status: str) -> None:
    texts = {
        "confirmed": "✅ Buyurtmangiz tasdiqlandi va tayyorlanmoqda.",
        "shipping": "🚚 Buyurtmangiz kuryerga berildi va yo'lda.",
        "delivered": "📬 Buyurtmangiz yetkazildi. Xaridingiz uchun rahmat!",
        "cancelled": "❌ Buyurtmangiz bekor qilindi.",
    }
    message = texts.get(status)
    if not message or order.user is None:
        return
    await notify.notify_user(
        bot,
        order.user.tg_id,
        f"{message}\n\n🧾 Buyurtma: <b>#{esc(order.code)}</b>",
    )


@router.callback_query(F.data.startswith("a:opaid:"))
async def cb_mark_paid(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    try:
        order_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    order = await orders_service.get_order(session, order_id)
    if order is None:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return

    await orders_service.mark_paid(session, order)
    await callback.answer("💵 To'lov qayd etildi")
    if order.user is not None:
        await notify.notify_user(
            bot,
            order.user.tg_id,
            f"✅ To'lov qabul qilindi: <b>#{esc(order.code)}</b>\n"
            f"Summa: <b>{money(order.total)}</b>",
        )
    await edit_or_send(callback, order_text(order, admin=True), order_admin_kb(order))


@router.callback_query(F.data.startswith("a:oref:"))
async def cb_refund(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    try:
        order_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    order = await orders_service.get_order(session, order_id)
    if order is None:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return
    if order.payment_method != "stars" or not order.charge_id:
        await callback.answer("Bu buyurtma Stars orqali to'lanmagan.", show_alert=True)
        return
    if order.payment_status != "paid":
        await callback.answer("To'lov qaytariladigan holatda emas.", show_alert=True)
        return
    if order.user is None:
        await callback.answer("Foydalanuvchi topilmadi.", show_alert=True)
        return

    try:
        refunded = await bot.refund_star_payment(order.user.tg_id, order.charge_id)
    except Exception as exc:
        log.exception("Star refund failed for order %s", order.code)
        await callback.answer(f"❌ Qaytarishda xatolik: {exc}", show_alert=True)
        return

    if not refunded:
        await callback.answer("❌ Telegram qaytarishni rad etdi.", show_alert=True)
        return

    await orders_service.mark_refunded(session, order)
    await callback.answer("↩️ Stars qaytarildi")
    await notify.notify_user(
        bot,
        order.user.tg_id,
        f"↩️ <b>#{esc(order.code)}</b> uchun to'lov qaytarildi.\n"
        f"Summa: <b>{money(order.total)}</b>",
    )
    await edit_or_send(callback, order_text(order, admin=True), order_admin_kb(order))
