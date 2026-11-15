"""Shopping cart and the checkout FSM."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.handlers.user.payments import send_order_invoice
from bot.keyboards import user as kb
from bot.models import Order, User
from bot.services import cart as cart_service
from bot.services import notify, orders as orders_service, settings_store
from bot.services.cart import summarize
from bot.services.orders import CheckoutData, Preview
from bot.states import Checkout
from bot.utils import (
    esc,
    money,
    normalize_phone,
    payment_label,
    payment_status_label,
    short,
    valid_phone,
)
from bot.views import cart_text, safe_delete, show_cart

router = Router(name="cart")


def _previous(callback: CallbackQuery) -> Message | None:
    return callback.message if isinstance(callback.message, Message) else None


async def _render_cart(
    callback: CallbackQuery, session: AsyncSession, user: User, bot: Bot
) -> None:
    items = await cart_service.get_items(session, user.id)
    shop = await settings_store.shop_config(session)
    summary = summarize(items, shop)
    text = cart_text(items, summary)
    markup = kb.cart_kb(items, summary, can_checkout=bool(items) and not summary.problems)
    message = _previous(callback)
    if message is not None and not message.photo and not message.document:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest:
            pass
    await show_cart(bot, callback.from_user.id, session, user, previous=message)


@router.message(F.text == kb.BTN_CART)
async def cart_button(
    message: Message, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    await state.clear()
    await show_cart(bot, message.chat.id, session, user)


@router.callback_query(F.data == "cart")
async def cb_cart(
    callback: CallbackQuery, session: AsyncSession, user: User, bot: Bot
) -> None:
    await callback.answer()
    await show_cart(
        bot, callback.from_user.id, session, user, previous=_previous(callback)
    )


@router.callback_query(F.data.startswith("ci:"))
async def cb_cart_item(
    callback: CallbackQuery, session: AsyncSession, user: User, bot: Bot
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    try:
        item_id, delta = int(parts[1]), int(parts[2])
    except ValueError:
        await callback.answer()
        return

    item = await cart_service.get_item(session, item_id, user.id)
    if item is None:
        await callback.answer("Bu mahsulot savatda yo'q.", show_alert=False)
        await _render_cart(callback, session, user, bot)
        return

    if delta == 0:
        await cart_service.remove(session, item)
        await callback.answer("🗑 Savatdan olib tashlandi")
    else:
        _, message = await cart_service.set_quantity(session, item, item.quantity + delta)
        await callback.answer(message[:190] if message else f"{max(1, item.quantity + delta)} dona")

    await _render_cart(callback, session, user, bot)


@router.callback_query(F.data == "cclear")
async def cb_clear_cart(
    callback: CallbackQuery, session: AsyncSession, user: User, bot: Bot
) -> None:
    await cart_service.clear(session, user.id)
    await callback.answer("🧹 Savat tozalandi")
    await _render_cart(callback, session, user, bot)


# --- checkout -------------------------------------------------------------


def _items_block(preview: Preview) -> str:
    lines: list[str] = []
    for product, quantity in preview.lines:
        lines.append(
            f"• {esc(short(product.title, 40))}\n"
            f"   {quantity} × {money(product.price)} = "
            f"<b>{money(product.price * quantity)}</b>"
        )
    return "\n".join(lines)


def _totals_block(preview: Preview) -> str:
    lines = ["────────────────", f"Mahsulotlar: {money(preview.subtotal)}"]
    if preview.discount:
        lines.append(f"Chegirma: −{money(preview.discount)}")
    delivery = "bepul 🎁" if preview.delivery_fee == 0 else money(preview.delivery_fee)
    lines.append(f"Yetkazish: {delivery}")
    lines.append(f"<b>Jami: {money(preview.total)}</b>")
    return "\n".join(lines)


async def _preview_from_state(session: AsyncSession, data: dict, promo: str | None = None):
    shop = await settings_store.shop_config(session)
    items = [(int(pid), int(qty)) for pid, qty in data.get("items", [])]
    preview = await orders_service.preview(session, items, shop, promo)
    return shop, preview


async def begin_checkout(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    items: list[list[int]] | list[tuple[int, int]],
    *,
    mode: str = "cart",
) -> None:
    shop = await settings_store.shop_config(session)
    preview = await orders_service.preview(
        session, [(int(pid), int(qty)) for pid, qty in items], shop
    )
    if not preview.lines:
        await bot.send_message(chat_id, "🛒 Savat bo'sh. Avval mahsulot tanlang.")
        return
    if preview.problems:
        await bot.send_message(
            chat_id,
            "⚠️ " + "\n⚠️ ".join(esc(problem) for problem in preview.problems),
        )
        return

    await state.clear()
    await state.update_data(
        items=[[product.id, quantity] for product, quantity in preview.lines],
        mode=mode,
        name=user.full_name or "",
        payment="cash",
    )
    await state.set_state(Checkout.name)
    await bot.send_message(
        chat_id,
        "🧾 <b>Buyurtma rasmiylashtirish</b> — 1/4\n\n"
        "🙋‍♂️ Qabul qiluvchining ismini yozing.\n"
        "<i>Ismingiz to'g'ri bo'lsa «⏭ O'tkazib yuborish» tugmasini bosing.</i>",
        reply_markup=kb.skip_reply_kb(),
    )


@router.callback_query(F.data == "checkout")
async def cb_checkout(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    items = await cart_service.get_items(session, user.id)
    if not items:
        await callback.answer("Savat bo'sh.", show_alert=True)
        return
    await callback.answer()
    if isinstance(callback.message, Message):
        await safe_delete(callback.message)
    await begin_checkout(
        bot,
        callback.from_user.id,
        state,
        session,
        user,
        [[item.product_id, item.quantity] for item in items],
        mode="cart",
    )


@router.message(Checkout.name, F.text)
async def step_name(message: Message, state: FSMContext, user: User) -> None:
    text = (message.text or "").strip()
    name = user.full_name if text == kb.BTN_SKIP else text
    if not name or not 2 <= len(name) <= 120:
        await message.answer("Ism kamida 2 ta belgidan iborat bo'lishi kerak.")
        return
    await state.update_data(name=name)
    await state.set_state(Checkout.phone)
    await message.answer(
        "📞 <b>2/4</b> — Telefon raqamingizni yuboring.\n"
        "Tugma orqali ulashishingiz yoki qo'lda yozishingiz mumkin.\n"
        "<i>Format: +998 90 123 45 67</i>",
        reply_markup=kb.phone_reply_kb(),
    )


@router.message(Checkout.phone)
async def step_phone(message: Message, state: FSMContext, user: User) -> None:
    phone = ""
    if message.contact is not None:
        owner = message.contact.user_id
        if owner not in (None, message.from_user.id):
            await message.answer("❗️ Faqat o'zingizning telefon raqamingizni ulashing.")
            return
        phone = message.contact.phone_number or ""
    elif (message.text or "").strip() == kb.BTN_SKIP and user.phone:
        phone = user.phone
    elif message.text:
        phone = message.text.strip()

    if not valid_phone(phone):
        await message.answer(
            "❗️ Telefon raqam noto'g'ri. Qaytadan yuboring yoki tugmadan foydalaning."
        )
        return

    user.phone = normalize_phone(phone)
    await state.update_data(phone=user.phone)
    await state.set_state(Checkout.address)
    await message.answer(
        "📍 <b>3/4</b> — Yetkazib berish manzilini yozing.\n"
        "Shahar, tuman, ko'cha va uy raqamini ko'rsating.\n"
        "Yoki lokatsiyani yuboring.",
        reply_markup=kb.address_reply_kb(),
    )


@router.message(Checkout.address)
async def step_address(message: Message, state: FSMContext, session: AsyncSession) -> None:
    address = ""
    if message.location is not None:
        lat, lon = message.location.latitude, message.location.longitude
        address = f"https://maps.google.com/?q={lat:.6f},{lon:.6f}"
    elif message.text:
        address = message.text.strip()

    if not address or not 5 <= len(address) <= 300:
        await message.answer("❗️ Manzilni to'liqroq yozing (5–300 belgi).")
        return

    await state.update_data(address=address)
    await state.set_state(Checkout.comment)
    await message.answer(
        "💬 <b>4/4</b> — Qo'shimcha izoh (ixtiyoriy).\n"
        "Masalan: «Eshikni qo'ng'iroq qiling» yoki kuryer uchun eslatma.\n"
        "Izoh kerak bo'lmasa «⏭ O'tkazib yuborish»ni bosing.",
        reply_markup=kb.skip_reply_kb(),
    )


@router.message(Checkout.comment)
async def step_comment(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    text = (message.text or "").strip()
    comment = "" if text == kb.BTN_SKIP else text[:300]
    await state.update_data(comment=comment)

    data = await state.get_data()
    shop, preview = await _preview_from_state(session, data)
    if not preview.lines:
        await state.clear()
        await message.answer("Savat bo'sh yoki mahsulotlar o'zgargan. Qaytadan boshlang.")
        return

    await state.set_state(Checkout.payment)
    await message.answer(
        "💳 <b>To'lov usulini tanlang</b>\n\n"
        f"{_items_block(preview)}\n\n{_totals_block(preview)}",
        reply_markup=kb.payment_kb(
            card_available=bool(shop.card_number),
            stars_enabled=settings.stars_rate > 0,
        ),
    )


def _contact_block(data: dict) -> str:
    lines = [
        f"🙋‍♂️ {esc(data.get('name', '—'))}",
        f"📞 {esc(data.get('phone', '—'))}",
        f"📍 {esc(data.get('address', '—'))}",
    ]
    if data.get("comment"):
        lines.append(f"💬 {esc(data['comment'])}")
    return "\n".join(lines)


async def _show_payment(
    bot: Bot, chat_id: int, session: AsyncSession, state: FSMContext
) -> None:
    data = await state.get_data()
    shop, preview = await _preview_from_state(session, data, data.get("promo"))
    await state.set_state(Checkout.payment)
    await bot.send_message(
        chat_id,
        "💳 <b>To'lov usulini tanlang</b>\n\n"
        f"{_items_block(preview)}\n\n{_totals_block(preview)}",
        reply_markup=kb.payment_kb(
            card_available=bool(shop.card_number),
            stars_enabled=settings.stars_rate > 0,
        ),
    )


async def _show_confirm(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    state: FSMContext,
    *,
    alert: str | None = None,
) -> None:
    data = await state.get_data()
    _, preview = await _preview_from_state(session, data, data.get("promo"))
    await state.set_state(Checkout.confirm)
    text = (
        "✅ <b>Buyurtmani tekshiring</b>\n\n"
        f"{_contact_block(data)}\n\n"
        f"💳 To'lov: {payment_label(data.get('payment', 'cash'))}\n\n"
        f"{_items_block(preview)}\n\n{_totals_block(preview)}"
    )
    if preview.promo_error:
        text += f"\n\n⚠️ Promokod: {esc(preview.promo_error)}"
    if alert:
        text = f"{alert}\n\n{text}"
    await bot.send_message(chat_id, text, reply_markup=kb.confirm_kb())


@router.callback_query(F.data.startswith("pay:"), Checkout.payment)
async def cb_payment_method(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    method = (callback.data or "").split(":", 1)[-1]
    if method not in orders_service.PAYMENT_METHODS:
        await callback.answer("Noto'g'ri usul.", show_alert=True)
        return
    data = await state.get_data()
    if not data.get("items"):
        await callback.answer("Seans eskirgan. Qaytadan boshlang.", show_alert=True)
        await state.clear()
        return
    await state.update_data(payment=method)
    await callback.answer()
    if isinstance(callback.message, Message):
        await safe_delete(callback.message)
    await _show_confirm(bot, callback.from_user.id, session, state)


@router.callback_query(F.data == "paymenu", Checkout.confirm)
async def cb_payment_menu(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await safe_delete(callback.message)
    await _show_payment(bot, callback.from_user.id, session, state)


async def _ask_promo(message: Message, state: FSMContext) -> None:
    await state.set_state(Checkout.promo)
    await message.answer(
        "🎟 <b>Promokod</b>\n\nKodni yuboring. Promokodni olib tashlash uchun «−» yozing.",
        reply_markup=kb.cancel_reply_kb(),
    )


@router.callback_query(F.data == "promo", Checkout.confirm)
async def cb_ask_promo(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await _ask_promo(callback.message, state)


@router.message(Checkout.promo, F.text)
async def step_promo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    code = (message.text or "").strip()
    if code == "−" or code == "-":
        await state.update_data(promo=None)
        await message.answer("Promokod olib tashlandi.")
        await _show_confirm(bot, message.chat.id, session, state)
        return

    data = await state.get_data()
    _, preview = await _preview_from_state(session, data, code)
    if preview.promo_error:
        await message.answer(f"❌ {esc(preview.promo_error)}\n\nBoshqa kod kiriting yoki «−» yozing.")
        return

    await state.update_data(promo=code.strip().upper())
    await message.answer(f"🎉 Promokod qabul qilindi: −{money(preview.discount)}")
    await _show_confirm(bot, message.chat.id, session, state)


@router.callback_query(F.data == "co:cancel")
async def cb_cancel_checkout(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    await state.clear()
    await callback.answer("Bekor qilindi")
    if isinstance(callback.message, Message):
        await safe_delete(callback.message)
        await bot.send_message(
            callback.from_user.id, "❌ Buyurtma bekor qilindi. Savat saqlanib qoldi."
        )
    await show_cart(bot, callback.from_user.id, session, user)


@router.callback_query(F.data == "conf:yes", Checkout.confirm)
async def cb_confirm_order(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    if not data.get("items"):
        await callback.answer("Seans eskirgan. Qaytadan boshlang.", show_alert=True)
        await state.clear()
        return

    shop, preview = await _preview_from_state(session, data, data.get("promo"))
    if preview.promo_error:
        await state.update_data(promo=None)
        await callback.answer("Promokod endi amal qilmaydi, olib tashlandi.", show_alert=True)
        if isinstance(callback.message, Message):
            await safe_delete(callback.message)
        await _show_confirm(bot, callback.from_user.id, session, state)
        return

    if preview.problems:
        await callback.answer("⚠️ " + preview.problems[0], show_alert=True)
        return
    if not preview.lines:
        await callback.answer("Mahsulotlar topilmadi. Qaytadan boshlang.", show_alert=True)
        await state.clear()
        return

    checkout = CheckoutData(
        contact_name=data.get("name") or user.full_name or "Mijoz",
        phone=data.get("phone") or user.phone or "",
        address=data.get("address") or "",
        comment=data.get("comment") or "",
        payment_method=data.get("payment", "cash"),
        promo_code=data.get("promo"),
    )
    result = await orders_service.create_order(
        session, user, preview.lines, checkout, shop
    )
    if result.error or result.order is None:
        await callback.answer(f"❌ {result.error}", show_alert=True)
        return

    order = result.order
    mode = data.get("mode", "cart")
    if mode == "cart":
        await cart_service.clear(session, user.id)

    await callback.answer("✅ Buyurtma qabul qilindi!")
    if isinstance(callback.message, Message):
        await safe_delete(callback.message)
    await state.clear()

    await notify.new_order(bot, order)
    await _send_order_created(bot, callback.from_user.id, order, shop)


async def _send_order_created(bot: Bot, chat_id: int, order: Order, shop) -> None:
    lines = [
        f"🎉 <b>Buyurtma #{order.code} qabul qilindi!</b>",
        "",
        f"💰 Jami: <b>{money(order.total)}</b>",
        f"💳 To'lov: {payment_label(order.payment_method)} · "
        f"{payment_status_label(order.payment_status)}",
        "",
    ]
    if order.payment_method == "stars":
        lines.append("⭐️ To'lovni yakunlash uchun quyidagi hisob-fakturani to'lang.")
    elif order.payment_method == "card":
        if shop.card_number:
            lines.append("💳 Karta raqami:")
            lines.append(f"<code>{esc(shop.card_number)}</code>")
            if shop.card_holder:
                lines.append(f"👤 {esc(shop.card_holder)}")
            lines.append(f"Summa: <b>{money(order.total)}</b>")
            lines.append("")
            lines.append("To'lovdan so'ng «🧾 To'lov chekini yuborish» tugmasini bosing.")
        else:
            lines.append("Operator to'lov rekvizitlarini yuboradi.")
    else:
        lines.append("🚚 Operator buyurtmani tasdiqlash uchun tez orada bog'lanadi.")

    await bot.send_message(
        chat_id,
        "\n".join(lines),
        reply_markup=kb.order_detail_kb(order),
    )
    if order.payment_method == "stars" and order.payment_status == "pending":
        await send_order_invoice(bot, chat_id, order)


# --- expired checkout callback fallbacks ---------------------------------


@router.callback_query(F.data.in_({"conf:yes", "paymenu", "promo"}))
async def cb_stale_checkout(callback: CallbackQuery) -> None:
    await callback.answer(
        "⌛️ Bu buyurtma seansi eskirgan. Iltimos, savatdan qaytadan boshlang.",
        show_alert=True,
    )
