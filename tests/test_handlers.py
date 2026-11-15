"""Dispatcher-level simulation: feeds real Updates through aiogram handlers.

No network is used: a fake ``BaseSession`` answers every Bot API call with a
canned object, and the updates are dispatched exactly like Telegram would.

Run:  python tests/test_handlers.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

TEST_DB = ROOT / "data" / "handler_test.db"
for suffix in ("", "-wal", "-shm"):
    try:
        Path(str(TEST_DB) + suffix).unlink()
    except FileNotFoundError:
        pass

os.environ["BOT_TOKEN"] = "123456789:AAFakeTokenForHandlerTest_1234567890"
os.environ["ADMIN_IDS"] = "123456789"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///data/handler_test.db"
os.environ["WEBAPP_ENABLED"] = "false"
os.environ["THROTTLE_LIMIT"] = "10000"
os.environ["REQUIRED_CHANNEL_ID"] = ""
os.environ["TIMEZONE"] = "Asia/Tashkent"

from aiogram import Bot  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.types import (  # noqa: E402
    CallbackQuery,
    Chat,
    Message,
    Update,
    User as TgUser,
)
from sqlalchemy import select  # noqa: E402

from bot.config import settings  # noqa: E402
from bot.db import SessionFactory, engine, init_db  # noqa: E402
from bot.main import create_dispatcher  # noqa: E402
from bot.models import Category, Order, Product  # noqa: E402
from bot.services import users as users_service  # noqa: E402

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
USER_ID = 555001
ADMIN_ID = 123456789
BOT_ID = 777000111

PASSED = 0


def ok(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    PASSED += 1
    print(f"  ✅ {label}")


def tg_user(user_id: int, *, first_name: str = "Ali", username: str | None = "ali") -> TgUser:
    return TgUser(id=user_id, is_bot=False, first_name=first_name, username=username)


class FakeSession(BaseSession):
    """Answers API calls locally and records them."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, Any]] = []
        self._message_id = 5000

    async def make_request(self, bot: Bot, method: Any, timeout: int | None = None):
        name = type(method).__name__
        self.calls.append((name, method))

        if name == "GetMe":
            return TgUser(
                id=BOT_ID, is_bot=True, first_name="ShopBot", username="shopbot"
            )

        if name in {
            "SendMessage",
            "SendPhoto",
            "SendDocument",
            "SendInvoice",
            "CopyMessage",
        }:
            self._message_id += 1
            return Message(
                message_id=self._message_id,
                date=NOW,
                chat=Chat(id=getattr(method, "chat_id", 0) or 0, type="private"),
                from_user=TgUser(
                    id=BOT_ID, is_bot=True, first_name="ShopBot", username="shopbot"
                ),
                text=getattr(method, "text", None),
                caption=getattr(method, "caption", None),
            )

        # Everything else (answers, edits, deletes, actions) returns True.
        return True

    async def stream_content(self, *args: Any, **kwargs: Any):
        if False:  # pragma: no cover - keeps this an async generator
            yield b""

    async def close(self) -> None:
        return None

    # --- helpers ---------------------------------------------------------

    def texts(self) -> list[str]:
        return [
            getattr(method, "text", None) or getattr(method, "caption", None) or ""
            for name, method in self.calls
            if name
            in {"SendMessage", "SendPhoto", "EditMessageText", "EditMessageCaption"}
        ]

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


class Harness:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.dp = create_dispatcher(bot)
        self._update_id = 1

    def _next(self) -> int:
        self._update_id += 1
        return self._update_id

    def base_message(
        self,
        *,
        chat_id: int,
        user_id: int,
        text: str | None = None,
        message_id: int = 1,
        first_name: str = "Ali",
        username: str | None = "ali",
    ) -> Message:
        return Message(
            message_id=message_id,
            date=NOW,
            chat=Chat(id=chat_id, type="private"),
            from_user=tg_user(user_id, first_name=first_name, username=username),
            text=text,
        )

    async def send(
        self,
        text: str,
        *,
        user_id: int = USER_ID,
        first_name: str = "Ali",
        username: str | None = "ali",
    ) -> Any:
        update = Update(
            update_id=self._next(),
            message=self.base_message(
                chat_id=user_id,
                user_id=user_id,
                text=text,
                message_id=self._update_id,
                first_name=first_name,
                username=username,
            ),
        )
        return await self.dp.feed_update(self.bot, update)

    async def callback(
        self, data: str, *, user_id: int = USER_ID, message_id: int = 900
    ) -> Any:
        update = Update(
            update_id=self._next(),
            callback_query=CallbackQuery(
                id=f"cb-{self._update_id}",
                from_user=tg_user(user_id),
                chat_instance="chat-instance",
                data=data,
                message=self.base_message(
                    chat_id=user_id,
                    user_id=user_id,
                    text="previous",
                    message_id=message_id,
                ),
            ),
        )
        return await self.dp.feed_update(self.bot, update)


async def seed() -> tuple[int, int]:
    async with SessionFactory() as session:
        await users_service.get_or_create(
            session, USER_ID, username="ali", full_name="Ali Valiyev"
        )
        await users_service.get_or_create(
            session, ADMIN_ID, username="boss", full_name="Admin Boss"
        )
        category = Category(title="Kiyimlar", emoji="👕")
        session.add(category)
        await session.flush()
        product = Product(
            category_id=category.id,
            title="Ko'ylak Premium",
            description="Paxta mato",
            price=150_000,
            old_price=200_000,
            stock=5,
        )
        session.add(product)
        await session.commit()
        return category.id, product.id


async def run() -> None:
    await init_db()
    category_id, product_id = await seed()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML, link_preview_is_disabled=True
        ),
    )
    fake = FakeSession()
    bot.session = fake

    harness = Harness(bot)

    print("\n[1] Customer: /start → catalog → product → cart")
    await harness.send("/start")
    ok(any("Do'kon" in text or "shop" in text.lower() for text in fake.texts()), "/start replied")

    await harness.callback("cats")
    ok("Katalog" in fake.texts()[-1], "categories screen")

    await harness.callback(f"cat:{category_id}:1")
    ok("Kiyimlar" in fake.texts()[-1] and "1 ta mahsulot" in fake.texts()[-1], "products list in category")

    await harness.callback(f"pr:{product_id}:cat:{category_id}:1")
    ok("Ko'ylak Premium" in fake.texts()[-1], "product card")

    await harness.callback(f"add:{product_id}")
    ok(fake.names()[-1] == "AnswerCallbackQuery", "add-to-cart answered")

    await harness.callback("cart")
    ok("Savat" in fake.texts()[-1] and "Ko'ylak" in fake.texts()[-1], "cart shows item")

    print("\n[2] Checkout FSM")
    await harness.callback("checkout")
    ok("1/4" in fake.texts()[-1], "name step")

    await harness.send("Ali Valiyev")
    ok("2/4" in fake.texts()[-1], "phone step")

    await harness.send("+998 90 123 45 67")
    ok("3/4" in fake.texts()[-1], "address step")

    await harness.send("Toshkent, Chilonzor 1-uy")
    ok("4/4" in fake.texts()[-1], "comment step")

    await harness.send("Eshikni qo'ng'iroq qiling")
    ok("To'lov usulini tanlang" in fake.texts()[-1], "payment step")

    await harness.callback("pay:cash")
    ok("Buyurtmani tekshiring" in fake.texts()[-1], "confirm step")

    await harness.callback("conf:yes")
    ok(any("qabul qilindi" in text for text in fake.texts()), "order accepted")

    async with SessionFactory() as session:
        orders = list((await session.execute(select(Order))).scalars())
        ok(len(orders) == 1, "order persisted through middleware commit")
        order = orders[0]
        ok(order.status == "new" and order.payment_method == "cash", "order fields")
        ok(order.phone.endswith("901234567"), "phone normalized")
        product = await session.get(Product, product_id)
        ok(product is not None and product.stock == 4, "stock decremented")
        ok(order.items and order.items[0].quantity == 1, "order item snapshot")

    async with SessionFactory() as session:
        user = await users_service.get_or_create(session, USER_ID)
        ok(user[0].phone is not None, "user phone saved")
        await session.commit()

    print("\n[3] Customer: orders list + cancel order")
    await harness.callback("orders:1")
    ok("Buyurtmalarim" in fake.texts()[-1] and "Jami: 1 ta" in fake.texts()[-1], "user orders list")

    await harness.callback(f"ord:{order.id}")
    ok("Buyurtma" in fake.texts()[-1], "order detail")

    print("\n[4] Admin: panel, stats, order status")
    fake.calls.clear()
    await harness.send("/admin", user_id=ADMIN_ID, first_name="Boss", username="boss")
    ok("Admin panel" in fake.texts()[-1], "admin panel opened")

    await harness.callback("a:stats", user_id=ADMIN_ID)
    ok(fake.names()[-1] == "EditMessageText", "stats rendered")

    await harness.callback("a:orders:all:1", user_id=ADMIN_ID)
    ok(fake.names()[-1] == "EditMessageText", "admin orders list")

    await harness.callback(f"a:order:{order.id}", user_id=ADMIN_ID)
    ok(fake.names()[-1] == "EditMessageText", "admin order detail")

    await harness.callback(f"a:ost:{order.id}:confirmed", user_id=ADMIN_ID)
    ok(any("Buyurtmangiz tasdiqlandi" in text for text in fake.texts()), "customer notified")

    async with SessionFactory() as session:
        fresh = await session.get(Order, order.id)
        ok(fresh is not None and fresh.status == "confirmed", "status persisted")

    print("\n[5] Admin: products + category CRUD FSM")
    await harness.callback("a:prods:1", user_id=ADMIN_ID)

    await harness.callback("a:pnew", user_id=ADMIN_ID)
    ok("Yangi mahsulot" in fake.texts()[-1], "category picker shown")

    await harness.callback(f"a:psetcat:0:{category_id}", user_id=ADMIN_ID)
    ok("1/7" in fake.texts()[-1], "product title step")

    await harness.send("Futbolka", user_id=ADMIN_ID, first_name="Boss", username="boss")
    await harness.send("⏭", user_id=ADMIN_ID, first_name="Boss", username="boss")
    await harness.send("120 000", user_id=ADMIN_ID, first_name="Boss", username="boss")
    await harness.send("150000", user_id=ADMIN_ID, first_name="Boss", username="boss")
    await harness.send("7", user_id=ADMIN_ID, first_name="Boss", username="boss")
    await harness.send("⏭", user_id=ADMIN_ID, first_name="Boss", username="boss")
    ok(any("Mahsulot qo'shildi" in text for text in fake.texts()), "product created via FSM")

    async with SessionFactory() as session:
        created = (
            await session.execute(select(Product).where(Product.title == "Futbolka"))
        ).scalar_one_or_none()
        ok(
            created is not None
            and created.price == 120_000
            and created.old_price == 150_000
            and created.stock == 7,
            "product fields saved",
        )

    await harness.callback("a:cnew", user_id=ADMIN_ID)
    ok("Yangi kategoriya" in fake.texts()[-1], "category form opened")
    await harness.send(
        "Aksessuarlar", user_id=ADMIN_ID, first_name="Boss", username="boss"
    )
    async with SessionFactory() as session:
        cat = (
            await session.execute(
                select(Category).where(Category.title == "Aksessuarlar")
            )
        ).scalar_one_or_none()
        ok(cat is not None, "category created via FSM")

    print("\n[6] Non-admin cannot open the admin panel")
    fake.calls.clear()
    await harness.callback("a:stats")
    ok("EditMessageText" not in fake.names(), "admin callbacks rejected for customer")

    print("\n[7] Profile and support flows")
    await harness.callback("profile")
    ok(fake.names()[-1] == "EditMessageText", "profile rendered")

    await harness.callback("support:msg")
    await harness.send("Savolim bor")
    ok(any("adminga yuborildi" in text for text in fake.texts()), "support message forwarded")

    await bot.session.close()
    await engine.dispose()
    print(f"\n🎉 ALL {PASSED} HANDLER CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(run())
