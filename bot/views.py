"""Message rendering helpers shared by user handlers."""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import user as kb
from bot.models import CartItem, Order, Product, User
from bot.services import cart as cart_service
from bot.services import catalog, favorites as fav_service, settings_store
from bot.services import orders as orders_service
from bot.services.cart import CartSummary, summarize
from bot.utils import (
    esc,
    fmt_dt,
    money,
    paginate,
    payment_label,
    payment_status_label,
    short,
    status_label,
)

MAX_CAPTION = 1024
MAX_TEXT = 4096


async def safe_delete(message: Message | None) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass


async def _send(
    bot: Bot,
    chat_id: int,
    *,
    text: str,
    photo: str | None = None,
    markup: InlineKeyboardMarkup | None = None,
    previous: Message | None = None,
) -> Message | None:
    if previous is not None:
        await safe_delete(previous)
    try:
        if photo:
            return await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=text[:MAX_CAPTION],
                reply_markup=markup,
            )
        return await bot.send_message(
            chat_id=chat_id, text=text[:MAX_TEXT], reply_markup=markup
        )
    except TelegramForbiddenError:
        return None
    except TelegramBadRequest:
        # Expired file_id or too-long text: degrade gracefully.
        try:
            return await bot.send_message(
                chat_id=chat_id, text=text[:MAX_TEXT], reply_markup=markup
            )
        except (TelegramBadRequest, TelegramForbiddenError):
            return None


async def show_home(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    user: User,
    *,
    previous: Message | None = None,
) -> Message | None:
    shop = await settings_store.shop_config(session)
    data = await settings_store.load_all(session)
    cart_count = await cart_service.count_positions(session, user.id)
    text = (
        f"🏪 <b>{esc(shop.shop_name)}</b>\n\n"
        f"🕘 Ish vaqti: {esc(data.get('work_hours', '—'))}\n"
        f"📦 Ombordagi mahsulotlar: {await catalog.in_stock_count(session)} ta\n\n"
        "Kerakli bo'limni tanlang 👇"
    )
    return await _send(bot, chat_id, text=text, markup=kb.home_kb(cart_count), previous=previous)


async def show_categories(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    user: User,
    *,
    previous: Message | None = None,
) -> Message | None:
    categories = await catalog.list_categories(session)
    cart_count = await cart_service.count_positions(session, user.id)
    if not categories:
        text = (
            "🛍 <b>Katalog</b>\n\nHozircha kategoriyalar qo'shilmagan.\n"
            "Tez orada mahsulotlar paydo bo'ladi!"
        )
        markup = kb.home_kb(cart_count)
    else:
        counts = await catalog.category_counts(session)
        text = "🛍 <b>Katalog</b>\n\nKerakli bo'limni tanlang 👇"
        markup = kb.categories_kb(categories, counts, cart_count)
    return await _send(bot, chat_id, text=text, markup=markup, previous=previous)


async def show_products(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    user: User,
    *,
    source: str,
    source_id: int = 0,
    page: int = 1,
    search: str | None = None,
    previous: Message | None = None,
) -> Message | None:
    product_list: list[Product] = []
    total = 0
    total_pages = 1

    if source == "cat":
        category = await catalog.get_category(session, source_id)
        if category is None:
            return await show_categories(bot, chat_id, session, user, previous=previous)
        header = f"{category.emoji} <b>{esc(category.title)}</b>"
        if category.description:
            header += f"\n{esc(short(category.description, 200))}"
        product_list, total, total_pages = await catalog.products_page(
            session, category_id=source_id, page=page, active_only=True
        )
    elif source == "search":
        header = f"🔍 <b>Qidiruv:</b> {esc(search or '')}"
        product_list, total, total_pages = await catalog.products_page(
            session, page=page, search=search or "", active_only=True
        )
    else:
        header = "🔥 <b>Barcha mahsulotlar</b>"
        product_list, total, total_pages = await catalog.products_page(
            session, page=page, active_only=True
        )

    if not product_list:
        text = header + "\n\n😔 Hech narsa topilmadi. Boshqa so'rov bilan urinib ko'ring."
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Kategoriyalar", callback_data="cats")]]
        )
    else:
        text = (
            f"{header}\n\n"
            f"📦 {total} ta mahsulot · {page}/{total_pages} sahifa\n\n"
            "Mahsulotni tanlang 👇"
        )
        markup = kb.products_kb(product_list, page, total_pages, source, source_id)
    return await _send(bot, chat_id, text=text, markup=markup, previous=previous)


async def show_product(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    user: User,
    product: Product,
    *,
    source: str = "all",
    source_id: int = 0,
    page: int = 1,
    previous: Message | None = None,
) -> Message | None:
    is_fav = await fav_service.is_favorite(session, user.id, product.id)
    category_line = ""
    if product.category is not None:
        category_line = f"\n🗂 {product.category.emoji} {esc(product.category.title)}"

    description = (product.description or "").strip()
    if len(description) > 600:
        description = description[:597] + "…"

    price_line = f"💰 <b>{money(product.price)}</b>"
    if product.old_price and product.old_price > product.price:
        price_line += f"  <s>{money(product.old_price)}</s> 🔥"

    stock_line = (
        f"📦 Omborda: <b>{product.stock}</b> dona"
        if product.stock > 0
        else "⛔️ <b>Omborda qolmagan</b>"
    )

    text = (
        f"<b>{esc(product.title)}</b>\n\n"
        f"{price_line}{category_line}\n"
        f"{stock_line}\n"
        f"⭐️ Sotilgan: {product.sales_count} dona\n"
    )
    if description:
        text += f"\n{esc(description)}\n"
    text += "\nSavatga qo'shishingiz yoki hoziroq buyurtma berishingiz mumkin 👇"

    markup = kb.product_kb(
        product, source=source, source_id=source_id, page=page, is_favorite=is_fav
    )
    return await _send(
        bot,
        chat_id,
        text=text,
        photo=product.photo_id,
        markup=markup,
        previous=previous,
    )


async def show_favorites(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    user: User,
    *,
    page: int = 1,
    previous: Message | None = None,
) -> Message | None:
    products, total_pages = await fav_service.page(session, user.id, page)
    if not products:
        text = (
            "❤️ <b>Saqlanganlar</b>\n\nHozircha bo'sh. "
            "Mahsulot kartasidagi ❤️ tugmasini bosing."
        )
        markup = kb.home_kb(await cart_service.count_positions(session, user.id))
    else:
        text = (
            "❤️ <b>Saqlanganlar</b>\n\n"
            f"{len(products)} ta mahsulot · {page}/{total_pages}\n\n"
            "Tanlang 👇"
        )
        markup = kb.favorites_kb(products, page, total_pages)
    return await _send(bot, chat_id, text=text, markup=markup, previous=previous)


def cart_text(items: list[CartItem], summary: CartSummary) -> str:
    if not items:
        return (
            "🛒 <b>Savat</b>\n\nSavat bo'sh.\n"
            "Katalogdan mahsulot tanlab, savatga qo'shing 👇"
        )

    lines = ["🛒 <b>Savat</b>\n"]
    for index, item in enumerate(items, 1):
        product = item.product
        if product is None:
            continue
        lines.append(
            f"{index}. {esc(short(product.title, 40))}\n"
            f"    {item.quantity} × {money(product.price)} = "
            f"<b>{money(product.price * item.quantity)}</b>"
        )
    lines.append("\n────────────────")
    lines.append(f"Mahsulotlar: {money(summary.subtotal)}")
    if summary.discount:
        lines.append(f"Chegirma: −{money(summary.discount)}")
    delivery = "bepul 🎁" if summary.delivery_fee == 0 else money(summary.delivery_fee)
    lines.append(f"Yetkazib berish: {delivery}")
    lines.append(f"<b>Jami: {money(summary.total)}</b>")
    if summary.problems:
        lines.append("\n⚠️ " + "\n⚠️ ".join(esc(problem) for problem in summary.problems))
    return "\n".join(lines)


async def show_cart(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    user: User,
    *,
    previous: Message | None = None,
) -> Message | None:
    items = await cart_service.get_items(session, user.id)
    shop = await settings_store.shop_config(session)
    summary = summarize(items, shop)
    can_checkout = bool(items) and not summary.problems and summary.total > 0
    return await _send(
        bot,
        chat_id,
        text=cart_text(items, summary),
        markup=kb.cart_kb(items, summary, can_checkout=can_checkout),
        previous=previous,
    )


async def show_orders(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    user: User,
    *,
    page: int = 1,
    previous: Message | None = None,
) -> Message | None:
    all_orders = await orders_service.user_orders(session, user.id, limit=60)
    page_items, page, total_pages = paginate(all_orders, page, 6)
    if not all_orders:
        text = "📦 <b>Buyurtmalarim</b>\n\nSizda hali buyurtmalar yo'q."
        markup = kb.home_kb(await cart_service.count_positions(session, user.id))
    else:
        text = (
            "📦 <b>Buyurtmalarim</b>\n\n"
            f"Jami: {len(all_orders)} ta · {page}/{total_pages}\n\n"
            "Tafsilotlarni ko'rish uchun tanlang 👇"
        )
        markup = kb.orders_kb(page_items, page, total_pages)
    return await _send(bot, chat_id, text=text, markup=markup, previous=previous)


def order_text(order: Order, *, admin: bool = False) -> str:
    lines = [
        f"🧾 <b>Buyurtma #{esc(order.code)}</b>",
        f"📅 {fmt_dt(order.created_at)}",
        f"📌 Holat: {status_label(order.status)}",
        f"💳 To'lov: {payment_label(order.payment_method)} · "
        f"{payment_status_label(order.payment_status)}",
        "",
    ]
    if admin and order.user is not None:
        username = f" @{esc(order.user.username)}" if order.user.username else ""
        lines.append(
            f'👤 <a href="tg://user?id={order.user.tg_id}">'
            f"{esc(order.user.full_name)}</a>{username} · <code>{order.user.tg_id}</code>"
        )
    lines.extend(
        [
            f"🙋‍♂️ Qabul qiluvchi: {esc(order.contact_name)}",
            f"📞 Telefon: {esc(order.phone)}",
            f"📍 Manzil: {esc(order.address)}",
        ]
    )
    if order.comment:
        lines.append(f"💬 Izoh: {esc(order.comment)}")
    lines.append("\n<b>Mahsulotlar:</b>")
    for item in order.items:
        lines.append(
            f"• {esc(short(item.title, 50))}\n"
            f"   {item.quantity} × {money(item.price)} = <b>{money(item.line_total)}</b>"
        )
    lines.append("────────────────")
    lines.append(f"Mahsulotlar: {money(order.subtotal)}")
    if order.discount:
        promo = f" ({esc(order.promo_code)})" if order.promo_code else ""
        lines.append(f"Chegirma{promo}: −{money(order.discount)}")
    delivery = "bepul 🎁" if order.delivery_fee == 0 else money(order.delivery_fee)
    lines.append(f"Yetkazish: {delivery}")
    lines.append(f"<b>Jami: {money(order.total)}</b>")
    return "\n".join(lines)


async def show_order(
    bot: Bot,
    chat_id: int,
    order: Order,
    *,
    previous: Message | None = None,
    admin: bool = False,
) -> Message | None:
    return await _send(
        bot,
        chat_id,
        text=order_text(order, admin=admin),
        markup=kb.order_detail_kb(order),
        previous=previous,
    )
