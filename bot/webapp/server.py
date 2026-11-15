"""Mini App backend: catalog API, photo proxy and validated checkout.

The HTTP API authenticates every request with Telegram ``initData`` (HMAC-SHA256
signed with the bot token), so it can never be used to place orders on behalf
of another user.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import parse_qsl

from aiogram import Bot
from aiogram.types import LabeledPrice
from aiohttp import web
from sqlalchemy import select

from bot.config import BASE_DIR, settings
from bot.db import SessionFactory
from bot.keyboards.user import order_detail_kb
from bot.models import Product
from bot.services import catalog, notify, settings_store
from bot.services import orders as orders_service
from bot.services import users as users_service
from bot.services.orders import CheckoutData
from bot.utils import money, stars_amount, valid_phone

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
PHOTO_DIR = BASE_DIR / "data" / "photos"
MAX_ITEMS = 30
MAX_QTY = 99
ORDER_RATE_LIMIT = 10  # per hour per user


# --- Telegram initData verification --------------------------------------


def validate_init_data(init_data: str, token: str, max_age: int = 86_400) -> dict | None:
    if not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    except ValueError:
        return None

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None

    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError:
        return None
    if not auth_date or time.time() - auth_date > max_age:
        return None

    try:
        user = json.loads(parsed.get("user", "{}"))
    except ValueError:
        return None
    if not isinstance(user, dict) or not user.get("id"):
        return None
    return user


# --- helpers --------------------------------------------------------------


def _json_error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": message}, status=status)


def _security_headers(response: web.StreamResponse) -> web.StreamResponse:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


async def index(request: web.Request) -> web.Response:
    response = web.FileResponse(STATIC_DIR / "index.html")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://telegram.org; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "frame-ancestors https://web.telegram.org https://*.telegram.org"
    )
    return _security_headers(response)


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def api_catalog(request: web.Request) -> web.Response:
    async with SessionFactory() as session:
        shop = await settings_store.shop_config(session)
        categories = await catalog.list_categories(session)
        products = list(
            (
                await session.execute(
                    select(Product)
                    .where(Product.is_active.is_(True))
                    .order_by(Product.id.desc())
                    .limit(300)
                )
            )
            .scalars()
            .all()
        )

    return web.json_response(
        {
            "ok": True,
            "shop": {
                "name": shop.shop_name,
                "currency": settings.shop_currency,
                "delivery_fee": shop.delivery_fee,
                "free_delivery_from": shop.free_delivery_from,
                "support": shop.support_username,
                "stars_rate": settings.stars_rate,
                "card_available": bool(shop.card_number),
            },
            "categories": [
                {
                    "id": category.id,
                    "title": category.title,
                    "emoji": category.emoji,
                }
                for category in categories
            ],
            "products": [
                {
                    "id": product.id,
                    "category_id": product.category_id,
                    "title": product.title,
                    "description": product.description,
                    "price": product.price,
                    "old_price": product.old_price,
                    "stock": product.stock,
                    "photo": f"/api/photo/{product.id}" if product.photo_id else None,
                }
                for product in products
            ],
        },
        headers={"Cache-Control": "no-store"},
    )


async def api_photo(request: web.Request) -> web.StreamResponse:
    bot: Bot = request.app["bot"]
    try:
        product_id = int(request.match_info["id"])
    except (KeyError, ValueError):
        raise web.HTTPNotFound()

    async with SessionFactory() as session:
        product = await session.get(Product, product_id)

    if product is None or not product.photo_id:
        raise web.HTTPNotFound()

    digest = hashlib.sha1(product.photo_id.encode()).hexdigest()[:10]
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    cached = PHOTO_DIR / f"{product_id}_{digest}.jpg"
    if not cached.exists():
        try:
            tg_file = await bot.get_file(product.photo_id)
            await bot.download_file(tg_file.file_path, destination=cached)
        except Exception:
            log.exception("Could not download product photo %s", product_id)
            raise web.HTTPNotFound()

    response = web.FileResponse(cached)
    response.headers["Cache-Control"] = "public, max-age=86400"
    return _security_headers(response)


_cart_limits: dict[int, deque[float]] = defaultdict(deque)


def _rate_limited(user_id: int) -> bool:
    now = time.monotonic()
    hits = _cart_limits[user_id]
    while hits and now - hits[0] > 3600:
        hits.popleft()
    if len(hits) >= ORDER_RATE_LIMIT:
        return True
    hits.append(now)
    if len(_cart_limits) > 2000:
        cutoff = now - 3600
        for key in [key for key, value in _cart_limits.items() if not value or value[-1] < cutoff]:
            _cart_limits.pop(key, None)
    return False


async def api_create_order(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    try:
        body = await request.json()
    except ValueError:
        return _json_error("Noto'g'ri so'rov.")

    tg_user = validate_init_data(str(body.get("initData", "")), settings.bot_token)
    if tg_user is None:
        return _json_error("Avtorizatsiya muvaffaqiyatsiz. Mini App'ni Telegram orqali oching.", 401)

    tg_id = int(tg_user["id"])
    if _rate_limited(tg_id):
        return _json_error("Juda ko'p so'rov. Bir oz kuting.", 429)

    raw_items = body.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return _json_error("Savat bo'sh.")

    items: list[tuple[int, int]] = []
    for entry in raw_items[:MAX_ITEMS]:
        if not isinstance(entry, dict):
            continue
        try:
            product_id = int(entry.get("id"))
            quantity = max(1, min(MAX_QTY, int(entry.get("qty", 1))))
        except (TypeError, ValueError):
            continue
        items.append((product_id, quantity))
    if not items:
        return _json_error("Mahsulotlar noto'g'ri.")

    name = str(body.get("name", "")).strip()[:120]
    phone = str(body.get("phone", "")).strip()[:32]
    address = str(body.get("address", "")).strip()[:300]
    comment = str(body.get("comment", "")).strip()[:300]
    payment = str(body.get("payment", "cash")).strip()
    promo = str(body.get("promo", "")).strip().upper()[:32] or None

    if not 2 <= len(name) <= 120:
        return _json_error("Ismni to'g'ri kiriting.")
    if not valid_phone(phone):
        return _json_error("Telefon raqam noto'g'ri.")
    if not 5 <= len(address) <= 300:
        return _json_error("Manzilni to'g'ri kiriting.")
    if payment not in orders_service.PAYMENT_METHODS:
        return _json_error("To'lov usuli noto'g'ri.")

    async with SessionFactory() as session:
        shop = await settings_store.shop_config(session)
        if payment == "card" and not shop.card_number:
            return _json_error("Karta to'lovi hozircha mavjud emas.")
        if payment == "stars" and settings.stars_rate <= 0:
            return _json_error("Stars to'lovi o'chirilgan.")

        user, _ = await users_service.get_or_create(
            session,
            tg_id,
            username=tg_user.get("username"),
            full_name=(
                f"{tg_user.get('first_name', '')} {tg_user.get('last_name', '')}".strip()
                or "Mijoz"
            ),
        )
        if user.is_blocked:
            return _json_error("Hisobingiz cheklangan. Qo'llab-quvvatlash bilan bog'laning.", 403)

        preview = await orders_service.preview(session, items, shop, promo)
        if preview.problems:
            return _json_error(preview.problems[0])
        if not preview.lines:
            return _json_error("Mahsulotlar topilmadi.")

        result = await orders_service.create_order(
            session,
            user,
            preview.lines,
            CheckoutData(
                contact_name=name,
                phone=phone,
                address=address,
                comment=comment,
                payment_method=payment,
                promo_code=promo if not preview.promo_error else None,
            ),
            shop,
        )
        if result.error or result.order is None:
            return _json_error(result.error or "Buyurtma yaratilmadi.")

        order = result.order
        await session.commit()
        order_id = order.id
        order_code = order.code
        order_total = order.total
        order_user_tg = user.tg_id

    invoice_link = None
    if payment == "stars":
        try:
            invoice_link = await bot.create_invoice_link(
                title=f"Buyurtma #{order_code}"[:32],
                description=f"Buyurtma #{order_code} · {money(order_total)}"[:255],
                payload=f"order:{order_id}",
                provider_token="",
                currency="XTR",
                prices=[
                    LabeledPrice(
                        label=f"Buyurtma #{order_code}", amount=stars_amount(order_total)
                    )
                ],
            )
        except Exception:
            log.exception("Could not create invoice link for order %s", order_code)

    async with SessionFactory() as session:
        full_order = await orders_service.get_order(session, order_id)
        if full_order is not None:
            await notify.new_order(bot, full_order)
            try:
                await bot.send_message(
                    order_user_tg,
                    f"🎉 <b>Buyurtma #{order_code} qabul qilindi!</b>\n\n"
                    f"💰 Jami: <b>{money(order_total)}</b>\n\n"
                    "Buyurtma holatini bot orqali kuzatishingiz mumkin.",
                    reply_markup=order_detail_kb(full_order),
                )
            except Exception:
                pass

    return web.json_response(
        {
            "ok": True,
            "code": order_code,
            "total": order_total,
            "payment": payment,
            "invoice_link": invoice_link,
        }
    )


async def create_app(bot: Bot) -> web.Application:
    app = web.Application(client_max_size=256 * 1024)
    app["bot"] = bot
    app.router.add_get("/", index)
    app.router.add_get("/healthz", health)
    app.router.add_get("/api/catalog", api_catalog)
    app.router.add_get("/api/photo/{id:\\d+}", api_photo)
    app.router.add_post("/api/order", api_create_order)
    app.router.add_static("/static/", STATIC_DIR, name="static", show_index=False)
    return app


async def start_webapp(bot: Bot) -> web.AppRunner:
    app = await create_app(bot)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, settings.webapp_host, settings.webapp_port)
    await site.start()
    return runner


async def stop_webapp(runner: web.AppRunner) -> None:
    await runner.cleanup()
