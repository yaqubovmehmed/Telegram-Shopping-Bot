"""Customer order history, cancellation and payment receipts."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards import user as kb
from bot.models import User
from bot.services import notify
from bot.services import orders as orders_service
from bot.states import Receipt
from bot.utils import esc, money
from bot.views import show_order, show_orders

router = Router(name="orders")


@router.message(F.text == kb.BTN_ORDERS)
async def orders_button(
    message: Message, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    await state.clear()
    await show_orders(bot, message.chat.id, session, user)


@router.callback_query(F.data.startswith("orders:"))
async def cb_orders(
    callback: CallbackQuery, session: AsyncSession, user: User, bot: Bot
) -> None:
    try:
        page = int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        page = 1
    await callback.answer()
    await show_orders(
        bot,
        callback.from_user.id,
        session,
        user,
        page=page,
        previous=callback.message if isinstance(callback.message, Message) else None,
    )


@router.callback_query(F.data.startswith("ord:"))
async def cb_order_detail(
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
    await callback.answer()
    await show_order(
        bot,
        callback.from_user.id,
        order,
        previous=callback.message if isinstance(callback.message, Message) else None,
    )


@router.callback_query(F.data.startswith("ordc:"))
async def cb_cancel_order(
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

    error = await orders_service.cancel_new_order(session, order)
    if error:
        await callback.answer(error, show_alert=True)
        return

    await callback.answer("❌ Buyurtma bekor qilindi", show_alert=True)
    await notify.notify_admins(
        bot,
        f"❌ <b>Mijoz buyurtmani bekor qildi</b>\n\n"
        f"#{order.code} · {user.full_name} ({user.tg_id})",
    )

    # Reload because set_status may have restocked products.
    order = await orders_service.get_order(session, order_id)
    await show_order(
        bot,
        callback.from_user.id,
        order,
        previous=callback.message if isinstance(callback.message, Message) else None,
    )


# --- payment receipt ------------------------------------------------------


@router.callback_query(F.data.startswith("rcpt:"))
async def cb_receipt(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User
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
    if order.payment_method != "card":
        await callback.answer("Bu buyurtma karta to'lovi emas.", show_alert=True)
        return

    await state.set_state(Receipt.photo)
    await state.update_data(receipt_order=order.id)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"🧾 <b>Buyurtma #{esc(order.code)}</b>\n\n"
            "To'lov chekini rasm yoki PDF fayl ko'rinishida yuboring.\n"
            f"Summa: <b>{money(order.total)}</b>",
            reply_markup=kb.cancel_reply_kb(),
        )


@router.message(Receipt.photo)
async def receipt_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    order_id = data.get("receipt_order")
    if not order_id:
        await state.clear()
        return
    order = await orders_service.get_order(session, int(order_id))
    if order is None or order.user_id != user.id:
        await state.clear()
        return

    if message.photo is None and message.document is None:
        await message.answer("❗️ Chekni rasm yoki PDF fayl ko'rinishida yuboring.")
        return

    admin_chat = settings.admin_log_chat_id or (settings.admin_ids[0] if settings.admin_ids else None)
    if admin_chat is not None:
        try:
            await bot.send_message(
                admin_chat,
                f"🧾 <b>To'lov cheki</b>\n\n"
                f"Buyurtma: <b>#{esc(order.code)}</b>\n"
                f"Summa: <b>{money(order.total)}</b>\n"
                f"Mijoz: {esc(user.full_name)} · <code>{user.tg_id}</code>",
            )
            await bot.copy_message(admin_chat, message.chat.id, message.message_id)
        except Exception:
            pass

    await state.clear()
    await message.answer(
        "✅ Chek qabul qilindi. Admin tekshirib, buyurtmani tasdiqlaydi.",
        reply_markup=kb.main_reply_kb(settings.is_admin(user.tg_id)),
    )
