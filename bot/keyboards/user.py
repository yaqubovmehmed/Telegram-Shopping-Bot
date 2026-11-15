"""Reusable keyboard builders (user facing)."""

from __future__ import annotations

from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot.config import settings
from bot.models import CartItem, Category, Order, Product
from bot.services.cart import CartSummary
from bot.utils import money, short, status_label

# --- reply keyboard labels ------------------------------------------------
BTN_CATALOG = "🛍 Katalog"
BTN_SEARCH = "🔍 Qidiruv"
BTN_CART = "🛒 Savat"
BTN_FAVS = "❤️ Saqlanganlar"
BTN_ORDERS = "📦 Buyurtmalarim"
BTN_PROFILE = "👤 Profil"
BTN_SUPPORT = "☎️ Yordam"

BTN_PHONE = "📱 Telefon raqamni ulashish"
BTN_LOCATION = "📍 Lokatsiyani yuborish"
BTN_SKIP = "⏭ O'tkazib yuborish"
BTN_CANCEL = "❌ Bekor qilish"
BTN_BACK = "⬅️ Orqaga"
BTN_MAIN_MENU = "🏠 Asosiy menyu"


def _btn(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _noop() -> InlineKeyboardButton:
    return _btn("·", "noop")


def pager(callback, page: int, total_pages: int) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if page > 1:
        row.append(_btn("◀️", callback(page - 1)))
    row.append(_btn(f"{page} / {total_pages}", "noop"))
    if page < total_pages:
        row.append(_btn("▶️", callback(page + 1)))
    return row


def main_reply_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=BTN_CATALOG), KeyboardButton(text=BTN_SEARCH))
    builder.row(KeyboardButton(text=BTN_CART), KeyboardButton(text=BTN_FAVS))
    builder.row(KeyboardButton(text=BTN_ORDERS), KeyboardButton(text=BTN_PROFILE))
    builder.row(KeyboardButton(text=BTN_SUPPORT))
    if is_admin:
        builder.row(KeyboardButton(text="🛠 Admin panel"))
    if settings.webapp_enabled and settings.webapp_url:
        builder.row(
            KeyboardButton(
                text="🚀 Mini App",
                web_app=WebAppInfo(url=settings.webapp_url),
            )
        )
    return builder.as_markup(resize_keyboard=True, input_field_placeholder="Menyudan tanlang…")


def cancel_reply_kb(extra: list[KeyboardButton] | None = None) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    if extra:
        builder.row(*extra)
    builder.row(KeyboardButton(text=BTN_CANCEL), KeyboardButton(text=BTN_MAIN_MENU))
    return builder.as_markup(resize_keyboard=True)


def phone_reply_kb() -> ReplyKeyboardMarkup:
    return cancel_reply_kb([KeyboardButton(text=BTN_PHONE, request_contact=True)])


def address_reply_kb() -> ReplyKeyboardMarkup:
    return cancel_reply_kb([KeyboardButton(text=BTN_LOCATION, request_location=True)])


def skip_reply_kb() -> ReplyKeyboardMarkup:
    return cancel_reply_kb([KeyboardButton(text=BTN_SKIP)])


def home_kb(cart_count: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("🛍 Katalog", "cats"),
        _btn(f"🛒 Savat ({cart_count})" if cart_count else "🛒 Savat", "cart"),
    )
    builder.row(
        _btn("📦 Buyurtmalarim", "orders:1"),
        _btn("❤️ Saqlanganlar", "favs:1"),
    )
    builder.row(
        _btn("👤 Profil", "profile"),
        _btn("☎️ Yordam", "support"),
    )
    if settings.webapp_enabled and settings.webapp_url:
        builder.row(
            InlineKeyboardButton(
                text="🚀 Mini App'da xarid qilish",
                web_app=WebAppInfo(url=settings.webapp_url),
            )
        )
    return builder.as_markup()


def categories_kb(
    categories: list[Category], counts: dict[int, int], cart_count: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        count = counts.get(category.id, 0)
        builder.button(
            text=f"{category.emoji} {category.title} · {count}",
            callback_data=f"cat:{category.id}:1",
        )
    builder.adjust(2)
    builder.row(_btn("🔥 Barcha mahsulotlar", "all:1"))
    if cart_count:
        builder.row(_btn(f"🛒 Savat ({cart_count})", "cart"))
    return builder.as_markup()


def back_callback(source: str, source_id: int, page: int) -> str:
    if source == "cat":
        return f"cat:{source_id}:{page}"
    if source == "fav":
        return f"favs:{page}"
    if source == "search":
        return "search:again"
    return f"all:{page}"


def list_page_callback(source: str, source_id: int):
    if source == "cat":
        return lambda p: f"cat:{source_id}:{p}"
    if source == "search":
        return lambda p: f"srch:{p}"
    return lambda p: f"all:{p}"


def products_kb(
    products: list[Product],
    page: int,
    total_pages: int,
    source: str,
    source_id: int = 0,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        if product.stock <= 0:
            badge = "⛔️"
        elif product.old_price:
            badge = "🔥"
        else:
            badge = "•"
        builder.row(
            _btn(
                f"{badge} {short(product.title, 28)} — {money(product.price)}",
                f"pr:{product.id}:{source}:{source_id}:{page}",
            )
        )
    if total_pages > 1:
        builder.row(*pager(list_page_callback(source, source_id), page, total_pages))
    builder.row(
        _btn("⬅️ Kategoriyalar", "cats"),
        _btn("🏠 Asosiy menyu", "menu"),
    )
    return builder.as_markup()


def product_kb(
    product: Product, *, source: str, source_id: int, page: int, is_favorite: bool
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    back_cb = back_callback(source, source_id, page)

    if product.stock > 0:
        builder.row(
            _btn("🛒 Savatga qo'shish", f"add:{product.id}"),
        )
        builder.row(_btn("⚡️ Hozir olish", f"buy:{product.id}"))
    else:
        builder.row(_btn("⛔️ Omborda qolmagan", "noop"))

    builder.row(
        _btn(
            "💔 Saqlanganlardan olib tashlash" if is_favorite else "❤️ Saqlash",
            f"fav:{product.id}:{source}:{source_id}:{page}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📤 Do'stga ulashish",
            switch_inline_query=f"p{product.id}",
        ),
        _btn("⬅️ Orqaga", back_cb),
    )
    return builder.as_markup()


def cart_kb(
    items: list[CartItem], summary: CartSummary, *, can_checkout: bool
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        product = item.product
        if product is None:
            continue
        builder.row(
            _btn("➖", f"ci:{item.id}:-1"),
            _btn(f"{item.quantity} × {money(product.price)}", "noop"),
            _btn("➕", f"ci:{item.id}:1"),
            _btn("🗑", f"ci:{item.id}:0"),
        )
    if items:
        builder.row(
            _btn("🧹 Savatni tozalash", "cclear"),
            _btn("🏠 Menyu", "menu"),
        )
        if can_checkout:
            builder.row(_btn(f"✅ Buyurtma berish · {money(summary.total)}", "checkout"))
    else:
        builder.row(_btn("🛍 Katalogga o'tish", "cats"))
    return builder.as_markup()


def payment_kb(card_available: bool, stars_enabled: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(_btn("💵 Naqd — yetkazib berishda", "pay:cash"))
    if card_available:
        builder.row(_btn("💳 Karta orqali o'tkazma", "pay:card"))
    if stars_enabled:
        builder.row(_btn("⭐️ Telegram Stars", "pay:stars"))
    builder.row(_btn("❌ Bekor qilish", "co:cancel"))
    return builder.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(_btn("✅ Buyurtmani tasdiqlash", "conf:yes"))
    builder.row(
        _btn("🎟 Promokod", "promo"),
        _btn("❌ Bekor qilish", "co:cancel"),
    )
    return builder.as_markup()


def orders_kb(orders: list[Order], page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        builder.row(
            _btn(
                f"#{order.code} · {status_label(order.status).split(' ', 1)[-1]} · {money(order.total)}",
                f"ord:{order.id}",
            )
        )
    if total_pages > 1:
        builder.row(*pager(lambda p: f"orders:{p}", page, total_pages))
    builder.row(_btn("🏠 Asosiy menyu", "menu"))
    return builder.as_markup()


def order_detail_kb(order: Order) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📋 Kodni nusxalash", copy_text=CopyTextButton(text=order.code)))
    if order.payment_method == "stars" and order.payment_status == "pending":
        builder.row(_btn("⭐️ To'lovni yakunlash", f"paystars:{order.id}"))
    if order.payment_method == "card" and order.payment_status == "pending":
        builder.row(_btn("🧾 To'lov chekini yuborish", f"rcpt:{order.id}"))
    if order.status in ("new", "confirmed"):
        builder.row(_btn("❌ Buyurtmani bekor qilish", f"ordc:{order.id}"))
    builder.row(
        _btn("📦 Barcha buyurtmalar", "orders:1"),
        _btn("☎️ Yordam", "support"),
    )
    return builder.as_markup()


def favorites_kb(products: list[Product], page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        builder.row(
            _btn(
                f"❤️ {short(product.title, 28)} — {money(product.price)}",
                f"pr:{product.id}:fav:0:{page}",
            )
        )
    if total_pages > 1:
        builder.row(*pager(lambda p: f"favs:{p}", page, total_pages))
    builder.row(_btn("🏠 Asosiy menyu", "menu"))
    return builder.as_markup()


def subscription_kb(channel_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if channel_url:
        builder.row(InlineKeyboardButton(text="📣 Kanalga obuna bo'lish", url=channel_url))
    builder.row(_btn("✅ Tekshirish", "sub:check"))
    return builder.as_markup()


def support_kb(support_username: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if support_username:
        username = support_username.lstrip("@")
        builder.row(InlineKeyboardButton(text="💬 Adminga yozish", url=f"https://t.me/{username}"))
    builder.row(_btn("✍️ Xabar qoldirish", "support:msg"))
    builder.row(_btn("🏠 Asosiy menyu", "menu"))
    return builder.as_markup()


def profile_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("📦 Buyurtmalarim", "orders:1"),
        _btn("❤️ Saqlanganlar", "favs:1"),
    )
    builder.row(_btn("☎️ Yordam", "support"))
    return builder.as_markup()
