"""FSM state groups."""

from aiogram.fsm.state import State, StatesGroup


class Checkout(StatesGroup):
    name = State()
    phone = State()
    address = State()
    comment = State()
    promo = State()
    payment = State()
    confirm = State()


class Search(StatesGroup):
    query = State()


class Support(StatesGroup):
    message = State()


class Receipt(StatesGroup):
    photo = State()


class ProductForm(StatesGroup):
    category = State()
    title = State()
    description = State()
    price = State()
    old_price = State()
    stock = State()
    photo = State()
    edit_value = State()


class CategoryForm(StatesGroup):
    title = State()


class PromoForm(StatesGroup):
    code = State()
    value = State()
    min_total = State()
    max_uses = State()
    days = State()


class ShopSettingForm(StatesGroup):
    value = State()


class BroadcastForm(StatesGroup):
    content = State()
