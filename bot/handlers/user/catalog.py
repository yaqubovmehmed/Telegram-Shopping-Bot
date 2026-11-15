"""Catalog browsing, product cards, search and wishlist."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import user as kb
from bot.models import User
from bot.services import cart as cart_service
from bot.services import catalog, favorites as fav_service
from bot.states import Search
from bot.views import show_categories, show_favorites, show_product, show_products

router = Router(name="catalog")


def _previous(callback: CallbackQuery) -> Message | None:
    return callback.message if isinstance(callback.message, Message) else None


@router.message(F.text == kb.BTN_CATALOG)
async def catalog_button(
    message: Message, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    await state.clear()
    await show_categories(bot, message.chat.id, session, user)


@router.callback_query(F.data == "cats")
async def cb_categories(
    callback: CallbackQuery, session: AsyncSession, user: User, bot: Bot
) -> None:
    await callback.answer()
    await show_categories(
        bot, callback.from_user.id, session, user, previous=_previous(callback)
    )


@router.callback_query(F.data.startswith("cat:"))
async def cb_category(
    callback: CallbackQuery, session: AsyncSession, user: User, bot: Bot
) -> None:
    await callback.answer()
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        return
    await show_products(
        bot,
        callback.from_user.id,
        session,
        user,
        source="cat",
        source_id=int(parts[1]),
        page=int(parts[2]),
        previous=_previous(callback),
    )


@router.callback_query(F.data.startswith("all:"))
async def cb_all_products(
    callback: CallbackQuery, session: AsyncSession, user: User, bot: Bot
) -> None:
    await callback.answer()
    page = _int_tail(callback.data, 1)
    await show_products(
        bot,
        callback.from_user.id,
        session,
        user,
        source="all",
        page=page,
        previous=_previous(callback),
    )


@router.callback_query(F.data.startswith("pr:"))
async def cb_product(
    callback: CallbackQuery, session: AsyncSession, user: User, bot: Bot
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        await callback.answer()
        return
    try:
        product_id = int(parts[1])
        source = parts[2]
        source_id = int(parts[3])
        page = int(parts[4])
    except ValueError:
        await callback.answer()
        return

    product = await catalog.get_product(session, product_id)
    if product is None or not product.is_active:
        await callback.answer("Mahsulot topilmadi yoki sotuvdan olingan.", show_alert=True)
        return
    await callback.answer()
    await show_product(
        bot,
        callback.from_user.id,
        session,
        user,
        product,
        source=source,
        source_id=source_id,
        page=page,
        previous=_previous(callback),
    )


@router.callback_query(F.data.startswith("add:"))
async def cb_add_to_cart(
    callback: CallbackQuery, session: AsyncSession, user: User
) -> None:
    product_id = _int_tail(callback.data, 0)
    if not product_id:
        await callback.answer()
        return
    _, message = await cart_service.add(session, user.id, product_id)
    await callback.answer(message[:190], show_alert=False)


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy_now(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    product_id = _int_tail(callback.data, 0)
    product = await catalog.get_product(session, product_id) if product_id else None
    if product is None or not product.is_active:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return
    if product.stock <= 0:
        await callback.answer("Afsuski, omborda qolmagan.", show_alert=True)
        return

    from bot.handlers.user.cart import begin_checkout

    await callback.answer()
    await begin_checkout(
        bot,
        callback.from_user.id,
        state,
        session,
        user,
        [[product.id, 1]],
        mode="buy",
    )


@router.callback_query(F.data.startswith("fav:"))
async def cb_toggle_favorite(
    callback: CallbackQuery, session: AsyncSession, user: User
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        await callback.answer()
        return
    try:
        product_id = int(parts[1])
        source = parts[2]
        source_id = int(parts[3])
        page = int(parts[4])
    except ValueError:
        await callback.answer()
        return

    product = await catalog.get_product(session, product_id)
    if product is None:
        await callback.answer("Mahsulot topilmadi.", show_alert=True)
        return

    is_fav = await fav_service.toggle(session, user.id, product_id)
    await callback.answer("❤️ Saqlanganlarga qo'shildi" if is_fav else "💔 Saqlanganlardan olib tashlandi")
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_reply_markup(
                reply_markup=kb.product_kb(
                    product,
                    source=source,
                    source_id=source_id,
                    page=page,
                    is_favorite=is_fav,
                )
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("favs:"))
async def cb_favorites(
    callback: CallbackQuery, session: AsyncSession, user: User, bot: Bot
) -> None:
    await callback.answer()
    await show_favorites(
        bot,
        callback.from_user.id,
        session,
        user,
        page=_int_tail(callback.data, 1),
        previous=_previous(callback),
    )


@router.message(F.text == kb.BTN_FAVS)
async def favorites_button(
    message: Message, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    await state.clear()
    await show_favorites(bot, message.chat.id, session, user)


# --- search ---------------------------------------------------------------


async def ask_search(message: Message, state: FSMContext) -> None:
    await state.set_state(Search.query)
    await state.update_data(search_query="")
    await message.answer(
        "🔍 <b>Qidiruv</b>\n\nMahsulot nomini yozing (kamida 2 ta belgi):",
        reply_markup=kb.cancel_reply_kb(),
    )


@router.message(F.text == kb.BTN_SEARCH)
async def search_button(message: Message, state: FSMContext) -> None:
    await ask_search(message, state)


@router.callback_query(F.data == "search:again")
async def cb_search_again(
    callback: CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await ask_search(callback.message, state)


@router.message(Search.query, F.text)
async def search_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    query = (message.text or "").strip()
    if len(query) < 2:
        await message.answer("Kamida 2 ta belgi kiriting.")
        return
    if len(query) > 60:
        query = query[:60]

    await state.update_data(search_query=query)
    await state.set_state(None)
    await show_products(
        bot,
        message.chat.id,
        session,
        user,
        source="search",
        search=query,
        page=1,
    )


@router.callback_query(F.data.startswith("srch:"))
async def cb_search_page(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    query = (data or {}).get("search_query", "")
    if not query:
        await callback.answer("Qidiruvni qaytadan boshlang.", show_alert=True)
        return
    await callback.answer()
    await show_products(
        bot,
        callback.from_user.id,
        session,
        user,
        source="search",
        search=query,
        page=_int_tail(callback.data, 1),
        previous=_previous(callback),
    )


def _int_tail(data: str | None, index: int) -> int:
    try:
        parts = (data or "").split(":")
        return int(parts[index])
    except (IndexError, ValueError):
        return 1
