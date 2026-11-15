"""Admin: product and category management."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.admin.common import cb_message, edit_or_send
from bot.keyboards.admin import (
    cancel_kb,
    categories_admin_kb,
    category_picker_kb,
    product_admin_kb,
    products_admin_kb,
)
from bot.models import Category, Product, User
from bot.services import catalog
from bot.states import CategoryForm, ProductForm
from bot.utils import esc, money, parse_int, short

router = Router(name="admin-products")

EDIT_LABELS = {
    "title": "Nomi",
    "description": "Tavsifi",
    "price": "Narxi (so'm)",
    "old_price": "Eski narx (0 — o'chirish)",
    "stock": "Ombordagi soni",
    "photo": "Rasm (photo yoki 0 — o'chirish)",
}


def product_text(product: Product) -> str:
    category = (
        f"{product.category.emoji} {esc(product.category.title)}"
        if product.category
        else "—"
    )
    lines = [
        f"🛍 <b>{esc(product.title)}</b>  <code>#{product.id}</code>",
        "",
        f"💰 Narx: <b>{money(product.price)}</b>",
    ]
    if product.old_price:
        lines.append(f"🏷 Eski narx: {money(product.old_price)}")
    lines.extend(
        [
            f"📦 Ombor: <b>{product.stock}</b> dona",
            f"🗂 Kategoriya: {category}",
            f"🖼 Rasm: {'bor ✅' if product.photo_id else 'yoq ❌'}",
            f"👁 Holat: {'🟢 sotuvda' if product.is_active else '⚪️ sotuvdan olingan'}",
            f"⭐️ Sotilgan: {product.sales_count} dona",
        ]
    )
    if product.description:
        lines.append(f"\n📝 {esc(short(product.description, 500))}")
    return "\n".join(lines)


async def _send_product(
    target: Message, product: Product, *, edit: bool = False
) -> None:
    text = product_text(product)
    markup = product_admin_kb(product)
    if edit:
        try:
            await target.edit_text(text, reply_markup=markup)
            return
        except Exception:
            pass
    await target.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("a:prods:"))
async def cb_products(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    try:
        page = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        page = 1
    await callback.answer()
    message = cb_message(callback)
    if message is None:
        return
    products, total, total_pages = await catalog.products_page(
        session, page=page, per_page=6, active_only=False
    )
    text = (
        "🛍 <b>Mahsulotlar</b>\n\n"
        f"Jami: {total} ta · {page}/{total_pages} sahifa\n\n"
        "Tahrirlash uchun mahsulotni tanlang 👇"
    )
    try:
        await message.edit_text(
            text, reply_markup=products_admin_kb(products, page, total_pages)
        )
    except Exception:
        await message.answer(
            text, reply_markup=products_admin_kb(products, page, total_pages)
        )


@router.callback_query(F.data.startswith("a:prod:"))
async def cb_product_detail(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    try:
        product_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    product = await catalog.get_product(session, product_id)
    if product is None:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return
    await callback.answer()
    message = cb_message(callback)
    if message is not None:
        await _send_product(message, product, edit=True)


# --- create ---------------------------------------------------------------


@router.callback_query(F.data == "a:pnew")
async def cb_new_product(callback: CallbackQuery, session: AsyncSession) -> None:
    categories = await catalog.list_categories(session, active_only=False)
    if not categories:
        await callback.answer(
            "Avval kategoriya qo'shing: 🗂 Kategoriyalar → ➕ Yangi kategoriya.",
            show_alert=True,
        )
        return
    await edit_or_send(
        callback,
        "🆕 <b>Yangi mahsulot</b>\n\nQaysi kategoriyaga qo'shamiz?",
        category_picker_kb(categories),
    )


@router.callback_query(F.data.startswith("a:psetcat:"))
async def cb_set_product_category(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer()
        return
    try:
        product_id = int(parts[2])
        category_id = int(parts[3])
    except ValueError:
        await callback.answer()
        return

    if product_id == 0:
        category = await catalog.get_category(session, category_id)
        if category is None:
            await callback.answer("Kategoriya topilmadi.", show_alert=True)
            return
        await callback.answer()
        await state.clear()
        await state.update_data(draft={"category_id": category_id})
        await state.set_state(ProductForm.title)
        message = cb_message(callback)
        if message is not None:
            await message.answer(
                f"🆕 <b>Yangi mahsulot</b> · {category.emoji} {esc(category.title)}\n\n"
                "1/7 — Mahsulot nomini yozing (2–120 belgi):",
                reply_markup=cancel_kb(),
            )
        return

    product = await catalog.get_product(session, product_id)
    if product is None:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return
    product.category_id = category_id or None
    await session.flush()
    await callback.answer("✅ Kategoriya o'zgartirildi.")
    message = cb_message(callback)
    if message is not None:
        await _send_product(message, product, edit=True)


@router.message(ProductForm.title, F.text)
async def new_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not 2 <= len(title) <= 120:
        await message.answer("❗️ Nom 2–120 belgi bo'lishi kerak.")
        return
    data = await state.get_data()
    draft = data.get("draft", {})
    draft["title"] = title
    await state.update_data(draft=draft)
    await state.set_state(ProductForm.description)
    await message.answer(
        "2/7 — Tavsifni yozing (yoki «⏭» bilan o'tkazing):",
        reply_markup=cancel_kb(),
    )


@router.message(ProductForm.description, F.text)
async def new_description(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    description = "" if text == "⏭" or text.lower() in {"skip", "-"} else text[:1500]
    data = await state.get_data()
    draft = data.get("draft", {})
    draft["description"] = description
    await state.update_data(draft=draft)
    await state.set_state(ProductForm.price)
    await message.answer(
        "3/7 — Narxini yozing (so'mda, masalan 150000):", reply_markup=cancel_kb()
    )


@router.message(ProductForm.price, F.text)
async def new_price(message: Message, state: FSMContext) -> None:
    price = parse_int(message.text or "")
    if price is None:
        await message.answer("❗️ Narxni butun son bilan yozing (masalan 150000).")
        return
    data = await state.get_data()
    draft = data.get("draft", {})
    draft["price"] = price
    await state.update_data(draft=draft)
    await state.set_state(ProductForm.old_price)
    await message.answer(
        "4/7 — Eski narx (chegirmani ko'rsatish uchun). "
        "Kerak bo'lmasa «⏭» yuboring:",
        reply_markup=cancel_kb(),
    )


@router.message(ProductForm.old_price, F.text)
async def new_old_price(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()
    draft = data.get("draft", {})
    if text == "⏭" or text.lower() in {"skip", "-", "0"}:
        draft["old_price"] = None
    else:
        value = parse_int(text)
        if value is None or value <= 0:
            await message.answer("❗️ Eski narxni butun son bilan yozing yoki «⏭» yuboring.")
            return
        draft["old_price"] = value
    await state.update_data(draft=draft)
    await state.set_state(ProductForm.stock)
    await message.answer("5/7 — Ombordagi sonini yozing:", reply_markup=cancel_kb())


@router.message(ProductForm.stock, F.text)
async def new_stock(message: Message, state: FSMContext) -> None:
    stock = parse_int(message.text or "", minimum=0, maximum=1_000_000)
    if stock is None:
        await message.answer("❗️ Ombor sonini butun son bilan yozing (0 ham bo'ladi).")
        return
    data = await state.get_data()
    draft = data.get("draft", {})
    draft["stock"] = stock
    await state.update_data(draft=draft)
    await state.set_state(ProductForm.photo)
    await message.answer(
        "6/7 — Mahsulot rasmini yuboring yoki «⏭» bilan o'tkazing:",
        reply_markup=cancel_kb(),
    )


@router.message(ProductForm.photo)
async def new_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    photo_id: str | None = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    elif message.text and (message.text.strip() == "⏭" or message.text.strip().lower() in {"skip", "-"}):
        photo_id = None
    else:
        await message.answer("❗️ Rasm yuboring yoki «⏭» bilan o'tkazing.")
        return

    data = await state.get_data()
    draft = data.get("draft", {})
    category_id = draft.get("category_id")
    category = await catalog.get_category(session, category_id) if category_id else None
    product = Product(
        category=category,
        category_id=category_id,
        title=draft.get("title", "Mahsulot"),
        description=draft.get("description", ""),
        price=int(draft.get("price", 0)),
        old_price=draft.get("old_price"),
        stock=int(draft.get("stock", 0)),
        photo_id=photo_id,
    )
    session.add(product)
    await session.flush()
    await state.clear()
    await message.answer("✅ Mahsulot qo'shildi!")
    await _send_product(message, product)


# --- edit -----------------------------------------------------------------


@router.callback_query(F.data.startswith("a:pedit:"))
async def cb_edit_product(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer()
        return
    try:
        product_id = int(parts[2])
    except ValueError:
        await callback.answer()
        return
    field = parts[3]

    product = await catalog.get_product(session, product_id)
    if product is None:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return

    if field == "category":
        categories = await catalog.list_categories(session, active_only=False)
        await edit_or_send(
            callback,
            "🗂 Yangi kategoriyani tanlang:",
            category_picker_kb(categories, product_id),
        )
        return

    label = EDIT_LABELS.get(field)
    if label is None:
        await callback.answer("Maydon topilmadi.", show_alert=True)
        return

    current = {
        "title": product.title,
        "description": product.description,
        "price": product.price,
        "old_price": product.old_price or 0,
        "stock": product.stock,
        "photo": "bor" if product.photo_id else "yo'q",
    }.get(field, "")

    await callback.answer()
    await state.set_state(ProductForm.edit_value)
    await state.update_data(edit_pid=product_id, edit_field=field)
    message = cb_message(callback)
    if message is not None:
        await message.answer(
            f"✏️ <b>{label}</b>\n\nJoriy qiymat: <code>{esc(current)}</code>\n\n"
            "Yangi qiymatni yuboring:",
            reply_markup=cancel_kb(),
        )


@router.message(ProductForm.edit_value)
async def save_edit(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    product_id = data.get("edit_pid")
    field = data.get("edit_field")
    product = await catalog.get_product(session, int(product_id)) if product_id else None
    if product is None or not field:
        await state.clear()
        return

    text = (message.text or "").strip()

    if field == "photo":
        if message.photo:
            product.photo_id = message.photo[-1].file_id
        elif text in {"0", "-"}:
            product.photo_id = None
        else:
            await message.answer("❗️ Rasm yuboring yoki 0 kiriting (o'chirish uchun).")
            return
    elif field == "title":
        if not 2 <= len(text) <= 120:
            await message.answer("❗️ Nom 2–120 belgi bo'lishi kerak.")
            return
        product.title = text
    elif field == "description":
        if text in {"0", "-"}:
            product.description = ""
        elif len(text) > 1500:
            await message.answer("❗️ Tavsif 1500 belgidan oshmasin.")
            return
        else:
            product.description = text
    elif field in {"price", "old_price", "stock"}:
        value = parse_int(text, minimum=0, maximum=1_000_000_000)
        if value is None:
            await message.answer("❗️ Butun son kiriting.")
            return
        if field == "price":
            product.price = value
        elif field == "stock":
            product.stock = value
        else:
            product.old_price = value or None
    else:
        await state.clear()
        return

    await session.flush()
    await state.clear()
    await message.answer("✅ Yangilandi.")
    await _send_product(message, product)


@router.callback_query(F.data.startswith("a:ptog:"))
async def cb_toggle_product(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    try:
        product_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    product = await catalog.get_product(session, product_id)
    if product is None:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return
    product.is_active = not product.is_active
    await session.flush()
    state_text = "🟢 sotuvda" if product.is_active else "⚪️ sotuvdan olindi"
    await callback.answer(f"Holat: {state_text}")
    message = cb_message(callback)
    if message is not None:
        await _send_product(message, product, edit=True)


@router.callback_query(F.data.startswith("a:pdel:"))
async def cb_delete_product_ask(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    product_id = _tail_int(callback.data)
    product = await catalog.get_product(session, product_id) if product_id else None
    if product is None:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return
    await edit_or_send(
        callback,
        f"🗑 <b>{esc(product.title)}</b> ni butunlay o'chirishni tasdiqlaysizmi?\n\n"
        "Bu amalni qaytarib bo'lmaydi.",
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    _btn("🗑 Ha, o'chirish", f"a:pdel2:{product.id}"),
                    _btn("⬅️ Yo'q", f"a:prod:{product.id}"),
                ]
            ]
        ),
    )


@router.callback_query(F.data.startswith("a:pdel2:"))
async def cb_delete_product(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    product_id = _tail_int(callback.data)
    product = await catalog.get_product(session, product_id) if product_id else None
    if product is None:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return
    title = product.title
    await session.delete(product)
    await session.flush()
    await callback.answer("🗑 O'chirildi")
    message = cb_message(callback)
    if message is not None:
        products, total, total_pages = await catalog.products_page(
            session, page=1, per_page=6, active_only=False
        )
        await message.answer(
            f"🗑 «{esc(title)}» o'chirildi.\n\n🛍 Mahsulotlar: {total} ta",
            reply_markup=products_admin_kb(products, 1, total_pages),
        )


# --- categories -----------------------------------------------------------


@router.callback_query(F.data == "a:cats")
async def cb_categories(callback: CallbackQuery, session: AsyncSession) -> None:
    categories = await catalog.list_categories(session, active_only=False)
    text = (
        "🗂 <b>Kategoriyalar</b>\n\n"
        + (
            "Holatni almashtirish uchun nomni, o'chirish uchun 🗑 ni bosing."
            if categories
            else "Hozircha kategoriyalar yo'q."
        )
    )
    await edit_or_send(callback, text, categories_admin_kb(categories))


@router.callback_query(F.data == "a:cnew")
async def cb_new_category(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(CategoryForm.title)
    message = cb_message(callback)
    if message is not None:
        await message.answer(
            "🗂 <b>Yangi kategoriya</b>\n\n"
            "Nomini emoji bilan yozing, masalan: <code>👕 Kiyimlar</code>",
            reply_markup=cancel_kb(),
        )


@router.message(CategoryForm.title, F.text)
async def save_category(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    raw = (message.text or "").strip()
    if not raw or len(raw) > 80:
        await message.answer("❗️ Nom 1–80 belgi bo'lishi kerak.")
        return

    emoji = "📦"
    title = raw
    parts = raw.split(maxsplit=1)
    if len(parts) == 2 and not parts[0][0].isalnum():
        emoji = parts[0][:16]
        title = parts[1].strip()

    category = Category(title=title[:80], emoji=emoji)
    session.add(category)
    await session.flush()
    await state.clear()

    categories = await catalog.list_categories(session, active_only=False)
    await message.answer(
        f"✅ Kategoriya qo'shildi: {category.emoji} {esc(category.title)}",
        reply_markup=categories_admin_kb(categories),
    )


@router.callback_query(F.data.startswith("a:ctog:"))
async def cb_toggle_category(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    category_id = _tail_int(callback.data)
    category = await catalog.get_category(session, category_id) if category_id else None
    if category is None:
        await callback.answer("Kategoriya topilmadi.", show_alert=True)
        return
    category.is_active = not category.is_active
    await session.flush()
    await callback.answer("🟢 Faol" if category.is_active else "⚪️ Nofaol")
    categories = await catalog.list_categories(session, active_only=False)
    await edit_or_send(
        callback,
        "🗂 <b>Kategoriyalar</b>\n\nHolatni almashtirish uchun nomni bosing.",
        categories_admin_kb(categories),
    )


@router.callback_query(F.data.startswith("a:cdel:"))
async def cb_delete_category_ask(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    category_id = _tail_int(callback.data)
    category = await catalog.get_category(session, category_id) if category_id else None
    if category is None:
        await callback.answer("Kategoriya topilmadi.", show_alert=True)
        return
    await edit_or_send(
        callback,
        f"🗑 <b>{category.emoji} {esc(category.title)}</b> o'chirilsinmi?\n\n"
        "Mahsulotlar o'chmaydi, faqat kategoriyasiz qoladi.",
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    _btn("🗑 Ha", f"a:cdel2:{category.id}"),
                    _btn("⬅️ Yo'q", "a:cats"),
                ]
            ]
        ),
    )


@router.callback_query(F.data.startswith("a:cdel2:"))
async def cb_delete_category(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    category_id = _tail_int(callback.data)
    category = await catalog.get_category(session, category_id) if category_id else None
    if category is None:
        await callback.answer("Kategoriya topilmadi.", show_alert=True)
        return
    await session.delete(category)
    await session.flush()
    await callback.answer("🗑 O'chirildi")
    categories = await catalog.list_categories(session, active_only=False)
    await edit_or_send(
        callback,
        "🗂 <b>Kategoriyalar</b>",
        categories_admin_kb(categories),
    )


def _btn(text: str, callback_data: str):
    from aiogram.types import InlineKeyboardButton

    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _tail_int(data: str | None) -> int:
    try:
        return int((data or "").split(":")[2])
    except (IndexError, ValueError):
        return 0
