"""End-to-end service smoke test (no Telegram network required).

Run:  python tests/test_smoke.py
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

TEST_DB = ROOT / "data" / "smoke_test.db"
for suffix in ("", "-wal", "-shm"):
    try:
        (Path(str(TEST_DB) + suffix)).unlink()
    except FileNotFoundError:
        pass

os.environ["BOT_TOKEN"] = "123456789:AAFakeTokenForSmokeTest_1234567890"
os.environ["ADMIN_IDS"] = "123456789"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///data/smoke_test.db"
os.environ["WEBAPP_ENABLED"] = "false"
os.environ["TIMEZONE"] = "Asia/Tashkent"

from sqlalchemy import select  # noqa: E402

from bot.config import settings  # noqa: E402
from bot.db import SessionFactory, engine, init_db  # noqa: E402
from bot.models import Category, Order, Product  # noqa: E402
from bot.services import cart as cart_service  # noqa: E402
from bot.services import catalog, favorites, orders, promo, settings_store  # noqa: E402
from bot.services import users as users_service  # noqa: E402
from bot.services.orders import CheckoutData  # noqa: E402
from bot.views import (  # noqa: E402
    order_text,
    show_cart,
    show_categories,
    show_favorites,
    show_home,
    show_order,
    show_orders,
    show_product,
    show_products,
)
from bot.webapp.server import create_app, validate_init_data  # noqa: E402
from bot.keyboards import user as ukb  # noqa: E402

PASSED = 0


def ok(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    PASSED += 1
    print(f"  ✅ {label}")


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_message(self, chat_id, text, reply_markup=None, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": text, "markup": reply_markup})
        return None

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": caption, "markup": reply_markup})
        return None


def check_callback_lengths(markup, label: str) -> None:
    if markup is None:
        return
    for row in getattr(markup, "inline_keyboard", []):
        for button in row:
            if button.callback_data:
                assert len(button.callback_data.encode()) <= 64, (
                    f"{label}: callback too long: {button.callback_data}"
                )


async def run() -> None:
    await init_db()
    bot = FakeBot()

    async with SessionFactory() as session:
        print("\n[1] Users & catalog")
        user, created = await users_service.get_or_create(
            session, 555001, username="tester", full_name="Test Mijoz"
        )
        ok(created and user.id > 0, "user created")
        admin_user, _ = await users_service.get_or_create(
            session, 123456789, username="admin", full_name="Admin"
        )

        category = Category(title="Kiyimlar", emoji="👕", description="Mavsumiy kiyimlar")
        session.add(category)
        await session.flush()

        product1 = Product(
            category_id=category.id,
            title="Ko'ylak Premium",
            description="Paxta mato, qulay.",
            price=150_000,
            old_price=200_000,
            stock=10,
            sales_count=3,
        )
        product2 = Product(category_id=category.id, title="Shim", price=250_000, stock=2)
        product3 = Product(category_id=category.id, title="Bosh kiyim", price=50_000, stock=0)
        session.add_all([product1, product2, product3])
        await session.flush()

        ok(len(await catalog.list_categories(session)) == 1, "categories listed")
        items, total, pages = await catalog.products_page(session, page=1)
        ok(total == 3 and len(items) == 3 and pages == 1, "products page")
        found, total_found, _ = await catalog.products_page(session, search="ko'ylak")
        ok(total_found == 1 and found[0].id == product1.id, "search by title")
        ok((await catalog.category_counts(session)).get(category.id) == 2, "in-stock counts")

        print("\n[2] Cart")
        added, message = await cart_service.add(session, user.id, product1.id, 2)
        ok(added == 2, "add two units")
        added, message = await cart_service.add(session, user.id, product2.id, 99)
        ok(added == 2, "stock cap respected")
        cart_items = await cart_service.get_items(session, user.id)
        shop = await settings_store.shop_config(session)
        from bot.services.cart import summarize

        summary = summarize(cart_items, shop)
        ok(summary.subtotal == 2 * 150_000 + 2 * 250_000, "subtotal")
        ok(summary.delivery_fee == 0, "free delivery above threshold")
        small_preview = await orders.preview(session, [(product1.id, 1)], shop)
        ok(small_preview.delivery_fee == shop.delivery_fee, "delivery fee below threshold")
        ok(summary.total == summary.subtotal + summary.delivery_fee, "cart total")

        print("\n[3] Promo codes")
        promocode, error = await promo.create(
            session, code="SMOKE10", kind="percent", value=10, min_total=100_000, max_uses=2
        )
        ok(promocode is not None and not error, "promo created")
        check = await promo.check(session, "smoke10", summary.subtotal)
        ok(check.ok and check.discount == summary.subtotal // 10, "promo discount 10%")
        bad = await promo.check(session, "NOPE", summary.subtotal)
        ok(not bad.ok, "unknown promo rejected")

        print("\n[4] Checkout preview + order")
        preview = await orders.preview(
            session,
            [(item.product_id, item.quantity) for item in cart_items],
            shop,
            "SMOKE10",
        )
        ok(preview.discount == check.discount, "preview discount")
        ok(not preview.problems, "no stock problems")

        result = await orders.create_order(
            session,
            user,
            preview.lines,
            CheckoutData(
                contact_name="Test Mijoz",
                phone="+998901234567",
                address="Toshkent, Chilonzor 1-uy",
                comment="Eshikni qo'ng'iroq qiling",
                payment_method="cash",
                promo_code="SMOKE10",
            ),
            shop,
        )
        ok(result.error is None and result.order is not None, "order created")
        order = result.order
        ok(order.total == preview.total, "order total matches preview")
        ok(len(order.items) == 2, "order items snapshot")

        await session.refresh(product1)
        await session.refresh(product2)
        ok(product1.stock == 8 and product2.stock == 0, "stock decremented atomically")
        ok(product1.sales_count == 5, "sales counter incremented")
        await session.refresh(promocode)
        ok(promocode.used_count == 1, "promo usage recorded")

        text = order_text(order, admin=True)
        ok(order.code in text and "Jami" in text, "order text renders")
        check_callback_lengths(ukb.order_detail_kb(order), "order kb")

        print("\n[5] Cancel restores stock")
        err = await orders.set_status(session, order, "cancelled")
        await session.refresh(product1)
        ok(err is None and product1.stock == 10, "cancel restocks")
        ok(order.payment_status == "pending", "cash order unpaid until delivered")
        err = await orders.set_status(session, order, "delivered")
        ok(err is not None, "cancelled order is final")

        print("\n[6] Oversell protection")
        product1.stock = 1
        await session.flush()
        bad_result = await orders.create_order(
            session,
            user,
            [(product1, 5)],
            CheckoutData(contact_name="X", phone="+998901112233", address="Manzil 1"),
            shop,
        )
        ok(bad_result.order is None and bad_result.error, "oversell blocked")

        print("\n[7] Favorites")
        ok(await favorites.toggle(session, user.id, product1.id), "favorite added")
        ok(await favorites.count(session, user.id) == 1, "favorite counted")
        ok(await favorites.toggle(session, user.id, product1.id) is False, "favorite removed")

        print("\n[8] Settings")
        await settings_store.set_value(session, "shop_name", "Smoke Shop")
        ok(await settings_store.get(session, "shop_name") == "Smoke Shop", "setting saved")
        ok(await settings_store.get_int(session, "delivery_fee") == 20000, "int setting")

        print("\n[9] Stats")
        stats = await orders.shop_stats(session)
        ok(stats.users_total == 2 and stats.orders_total >= 1, "stats counters")
        ok(stats.status_counts.get("cancelled") == 1, "status breakdown")

        print("\n[10] Views")
        await show_home(bot, user.tg_id, session, user)
        await show_categories(bot, user.tg_id, session, user)
        await show_products(bot, user.tg_id, session, user, source="cat", source_id=category.id)
        await show_products(bot, user.tg_id, session, user, source="all")
        await show_products(bot, user.tg_id, session, user, source="search", search="shim")
        await show_product(bot, user.tg_id, session, user, product1, source="cat", source_id=category.id)
        await show_favorites(bot, user.tg_id, session, user)
        await show_cart(bot, user.tg_id, session, user)
        await show_orders(bot, user.tg_id, session, user)
        await show_order(bot, user.tg_id, order)
        ok(len(bot.sent) >= 10, "views produced messages")

        print("\n[11] Keyboards")
        from bot.keyboards import admin as akb
        from bot.services.settings_store import load_all

        products, _, _ = await catalog.products_page(session, page=1)
        promos = await promo.list_all(session)
        category_list = await catalog.list_categories(session)
        markups = {
            "home": ukb.home_kb(2),
            "main reply": ukb.main_reply_kb(True),
            "phone": ukb.phone_reply_kb(),
            "address": ukb.address_reply_kb(),
            "categories": ukb.categories_kb(category_list, {}, 2),
            "products": ukb.products_kb(products, 1, 2, "cat", category.id),
            "product": ukb.product_kb(product1, source="cat", source_id=category.id, page=1, is_favorite=False),
            "cart": ukb.cart_kb(cart_items, summary, can_checkout=True),
            "payment": ukb.payment_kb(True),
            "confirm": ukb.confirm_kb(),
            "orders": ukb.orders_kb([order], 1, 1),
            "order": ukb.order_detail_kb(order),
            "favorites": ukb.favorites_kb(products, 1, 1),
            "support": ukb.support_kb("@support"),
            "profile": ukb.profile_kb(),
            "subscription": ukb.subscription_kb("https://t.me/example"),
            "admin panel": akb.panel_kb(3),
            "admin orders": akb.orders_list_kb([order], "all", 1, 1, {"new": 1}),
            "admin order": akb.order_admin_kb(order),
            "admin products": akb.products_admin_kb(products, 1, 1),
            "admin product": akb.product_admin_kb(product1),
            "admin cats": akb.categories_admin_kb(category_list),
            "admin promos": akb.promos_admin_kb(promos),
            "admin settings": akb.settings_kb(await load_all(session)),
            "admin broadcast": akb.broadcast_confirm_kb(),
        }
        for name, markup in markups.items():
            check_callback_lengths(markup, name)
        ok(True, "all keyboards built, callbacks <= 64 bytes")

        print("\n[12] Mini App initData signature")
        token = settings.bot_token
        tg_user = json.dumps({"id": 555001, "first_name": "Test"}, separators=(",", ":"))
        params = {
            "auth_date": str(int(time.time())),
            "query_id": "AAHdF6IQAAAAAN0",
            "user": tg_user,
        }
        data_check = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        signature = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        good = urlencode({**params, "hash": signature})
        parsed = validate_init_data(good, token)
        ok(parsed is not None and parsed["id"] == 555001, "valid initData accepted")
        ok(validate_init_data(good.replace(signature, "0" * 64), token) is None, "bad hash rejected")
        old = str(int(time.time()) - 200_000)
        old_check = "\n".join(
            f"{key}={value}" for key, value in sorted({**params, "auth_date": old}.items())
        )
        old_sig = hmac.new(secret, old_check.encode(), hashlib.sha256).hexdigest()
        ok(validate_init_data(urlencode({**params, "auth_date": old, "hash": old_sig}), token) is None, "expired initData rejected")

        print("\n[13] Mini App HTTP app")
        app = await create_app(bot)
        routes = {route.resource.canonical for route in app.router.routes() if route.resource}
        ok("/api/catalog" in routes and "/api/order" in routes, "API routes registered")

        await session.commit()

    async with SessionFactory() as session:
        codes = list((await session.execute(select(Order.code))).scalars())
        ok(len(codes) == 1 and all(len(code) <= 16 for code in codes), "unique short order code")

    await engine.dispose()
    print(f"\n🎉 ALL {PASSED} CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(run())
