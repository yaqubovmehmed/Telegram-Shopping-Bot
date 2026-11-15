"""Admin panel keyboards."""

from __future__ import annotations

from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.models import Category, Order, Product, PromoCode
from bot.services.settings_store import SETTING_FIELDS
from bot.utils import money, short, status_label

ADMIN_BTN = "🛠 Admin panel"

FILTERS: tuple[tuple[str, str], ...] = (
    ("all", "🗂 Barchasi"),
    ("new", "🆕 Yangi"),
    ("confirmed", "✅ Tasdiq"),
    ("shipping", "🚚 Yo'lda"),
    ("delivered", "📬 Yetkazilgan"),
    ("cancelled", "❌ Bekor"),
)


def _btn(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def panel_kb(active_orders: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("📊 Statistika", "a:stats"),
        _btn(f"📦 Buyurtmalar · {active_orders}", "a:orders:all:1"),
    )
    builder.row(
        _btn("🛍 Mahsulotlar", "a:prods:1"),
        _btn("🗂 Kategoriyalar", "a:cats"),
    )
    builder.row(
        _btn("🎟 Promokodlar", "a:promos"),
        _btn("📢 Xabar yuborish", "a:bcast"),
    )
    builder.row(_btn("⚙️ Sozlamalar", "a:settings"))
    return builder.as_markup()


def orders_list_kb(
    orders: list[Order],
    status: str,
    page: int,
    total_pages: int,
    counts: dict[str, int],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        title = f"#{order.code} · {short(order.contact_name, 16)} · {money(order.total)}"
        builder.row(_btn(f"{title} · {status_label(order.status)}", f"a:order:{order.id}"))

    filters: list[InlineKeyboardButton] = []
    for key, label in FILTERS:
        count = counts.get(key, 0) if key != "all" else sum(counts.values())
        suffix = f" · {count}" if count else ""
        mark = "• " if key == status else ""
        filters.append(_btn(f"{mark}{label}{suffix}", f"a:orders:{key}:1"))
    builder.row(*filters[:3])
    builder.row(*filters[3:])

    if total_pages > 1:
        pager: list[InlineKeyboardButton] = []
        if page > 1:
            pager.append(_btn("◀️", f"a:orders:{status}:{page - 1}"))
        pager.append(_btn(f"{page} / {total_pages}", "a:noop"))
        if page < total_pages:
            pager.append(_btn("▶️", f"a:orders:{status}:{page + 1}"))
        builder.row(*pager)
    builder.row(_btn("🏠 Admin panel", "a:home"))
    return builder.as_markup()


def orders_filter_kb(
    status: str, page: int, total_pages: int, counts: dict[str, int]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    row: list[InlineKeyboardButton] = []
    for key, label in FILTERS:
        count = counts.get(key) if key != "all" else sum(counts.values())
        suffix = f" · {count}" if count else ""
        mark = "• " if key == status else ""
        row.append(_btn(f"{mark}{label}{suffix}", f"a:orders:{key}:1"))
    builder.row(*row[:3])
    builder.row(*row[3:])
    if total_pages > 1:
        pager: list[InlineKeyboardButton] = []
        if page > 1:
            pager.append(_btn("◀️", f"a:orders:{status}:{page - 1}"))
        pager.append(_btn(f"{page} / {total_pages}", "a:noop"))
        if page < total_pages:
            pager.append(_btn("▶️", f"a:orders:{status}:{page + 1}"))
        builder.row(*pager)
    builder.row(_btn("🏠 Admin panel", "a:home"))
    return builder.as_markup()


def order_admin_kb(order: Order) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    transitions: list[InlineKeyboardButton] = []
    if order.status == "new":
        transitions.append(_btn("✅ Tasdiqlash", f"a:ost:{order.id}:confirmed"))
    if order.status in ("new", "confirmed"):
        transitions.append(_btn("🚚 Yetkazishga berish", f"a:ost:{order.id}:shipping"))
    if order.status == "shipping":
        transitions.append(_btn("📬 Yetkazildi", f"a:ost:{order.id}:delivered"))
    if order.status not in ("delivered", "cancelled"):
        transitions.append(_btn("❌ Bekor qilish", f"a:ost:{order.id}:cancelled"))
    if transitions:
        builder.row(*transitions)

    extra: list[InlineKeyboardButton] = []
    if order.payment_status == "pending" and order.payment_method != "stars":
        extra.append(_btn("💵 To'landi deb belgilash", f"a:opaid:{order.id}"))
    if order.payment_status == "paid" and order.payment_method == "stars" and order.charge_id:
        extra.append(_btn("↩️ Starsni qaytarish", f"a:oref:{order.id}"))
    if extra:
        builder.row(*extra)

    builder.row(
        InlineKeyboardButton(
            text="📋 Kodni nusxalash", copy_text=CopyTextButton(text=order.code)
        ),
        InlineKeyboardButton(
            text="📞 Telefonni nusxalash", copy_text=CopyTextButton(text=order.phone)
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="👤 Foydalanuvchi", url=f"tg://user?id={order.user.tg_id}"
        )
    )
    builder.row(
        _btn("🧾 Buyurtmalar", "a:orders:all:1"),
        _btn("🏠 Admin panel", "a:home"),
    )
    return builder.as_markup()


def products_admin_kb(
    products: list[Product], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        state = "🟢" if product.is_active else "⚪️"
        stock = "⛔️" if product.stock <= 0 else f"{product.stock} dona"
        builder.row(
            _btn(
                f"{state} {short(product.title, 24)} · {money(product.price)} · {stock}",
                f"a:prod:{product.id}",
            )
        )
    if total_pages > 1:
        pager: list[InlineKeyboardButton] = []
        if page > 1:
            pager.append(_btn("◀️", f"a:prods:{page - 1}"))
        pager.append(_btn(f"{page} / {total_pages}", "a:noop"))
        if page < total_pages:
            pager.append(_btn("▶️", f"a:prods:{page + 1}"))
        builder.row(*pager)
    builder.row(
        _btn("➕ Yangi mahsulot", "a:pnew"),
        _btn("🏠 Admin panel", "a:home"),
    )
    return builder.as_markup()


def product_admin_kb(product: Product) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("✏️ Nomi", f"a:pedit:{product.id}:title"),
        _btn("📝 Tavsifi", f"a:pedit:{product.id}:description"),
    )
    builder.row(
        _btn("💰 Narxi", f"a:pedit:{product.id}:price"),
        _btn("🏷 Eski narx", f"a:pedit:{product.id}:old_price"),
    )
    builder.row(
        _btn("📦 Ombor", f"a:pedit:{product.id}:stock"),
        _btn("🖼 Rasm", f"a:pedit:{product.id}:photo"),
    )
    builder.row(_btn("🗂 Kategoriya", f"a:pedit:{product.id}:category"))
    builder.row(
        _btn(
            "⚪️ Sotuvdan olish" if product.is_active else "🟢 Sotuvga qaytarish",
            f"a:ptog:{product.id}",
        ),
        _btn("🗑 O'chirish", f"a:pdel:{product.id}"),
    )
    builder.row(
        _btn("🛍 Mahsulotlar", "a:prods:1"),
        _btn("🏠 Admin panel", "a:home"),
    )
    return builder.as_markup()


def category_picker_kb(categories: list[Category], product_id: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.row(
            _btn(
                f"{category.emoji} {category.title}",
                f"a:psetcat:{product_id}:{category.id}",
            )
        )
    if product_id:
        builder.row(_btn("🗑 Kategoriyani olib tashlash", f"a:psetcat:{product_id}:0"))
    builder.row(_btn("⬅️ Orqaga", f"a:prod:{product_id}" if product_id else "a:prods:1"))
    return builder.as_markup()


def categories_admin_kb(categories: list[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        state = "🟢" if category.is_active else "⚪️"
        builder.row(
            _btn(f"{state} {category.emoji} {category.title}", f"a:ctog:{category.id}"),
            _btn("🗑", f"a:cdel:{category.id}"),
        )
    builder.row(
        _btn("➕ Yangi kategoriya", "a:cnew"),
        _btn("🏠 Admin panel", "a:home"),
    )
    return builder.as_markup()


def promos_admin_kb(promos: list[PromoCode]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for promo in promos:
        state = "🟢" if promo.is_active else "⚪️"
        value = f"{promo.value}%" if promo.kind == "percent" else money(promo.value)
        builder.row(
            _btn(f"{state} {promo.code} · {value}", f"a:ptogpromo:{promo.id}"),
            _btn("🗑", f"a:pdelpromo:{promo.id}"),
        )
    builder.row(
        _btn("➕ Yangi promokod", "a:pnewpromo"),
        _btn("🏠 Admin panel", "a:home"),
    )
    return builder.as_markup()


def settings_kb(data: dict[str, str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for field in SETTING_FIELDS:
        value = data.get(field.key, "")
        if field.kind == "int":
            try:
                display = money(int(value or 0))
            except ValueError:
                display = value or "—"
        else:
            display = short(str(value), 24) or "—"
        builder.row(_btn(f"{field.label}: {display}", f"a:set:{field.key}"))
    builder.row(_btn("🏠 Admin panel", "a:home"))
    return builder.as_markup()


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(_btn("🚀 Yuborish", "a:bcast_send"))
    builder.row(_btn("❌ Bekor qilish", "a:home"))
    return builder.as_markup()


def back_kb(callback_data: str = "a:home", text: str = "⬅️ Orqaga") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn(text, callback_data)]])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("❌ Bekor qilish", "a:home")]])
