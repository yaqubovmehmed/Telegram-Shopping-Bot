"""Key/value shop configuration with a tiny read cache."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.models import Setting

DEFAULTS: dict[str, str] = {
    "shop_name": "Online Shopping",
    "welcome_text": (
        "Assalomu alaykum, <b>{name}</b>! 👋\n\n"
        "Bizning do'konimizga xush kelibsiz. Bu yerda siz o'zingizga yoqqan "
        "mahsulotni tanlab, bir necha daqiqada buyurtma berishingiz mumkin."
    ),
    "support_username": settings.support_username,
    "delivery_fee": "20000",
    "free_delivery_from": "500000",
    "card_number": "",
    "card_holder": "",
    "work_hours": "09:00 – 21:00",
    "channel_url": settings.required_channel_url,
}

_CACHE_TTL = 30.0
_cache: dict[str, str] | None = None
_cache_at: float = 0.0


def invalidate_cache() -> None:
    global _cache, _cache_at
    _cache = None
    _cache_at = 0.0


async def load_all(session: AsyncSession) -> dict[str, str]:
    global _cache, _cache_at
    if _cache is not None and time.monotonic() - _cache_at < _CACHE_TTL:
        return _cache

    rows = (await session.execute(select(Setting))).scalars().all()
    data = dict(DEFAULTS)
    data.update({row.key: row.value for row in rows})
    _cache = data
    _cache_at = time.monotonic()
    return data


async def get(session: AsyncSession, key: str) -> str:
    data = await load_all(session)
    return data.get(key, DEFAULTS.get(key, ""))


async def get_int(session: AsyncSession, key: str) -> int:
    try:
        return int(await get(session, key))
    except (TypeError, ValueError):
        return int(DEFAULTS.get(key, "0") or 0)


async def set_value(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
    await session.flush()
    invalidate_cache()


@dataclass(frozen=True, slots=True)
class ShopConfig:
    shop_name: str
    support_username: str
    delivery_fee: int
    free_delivery_from: int
    card_number: str
    card_holder: str


async def shop_config(session: AsyncSession) -> ShopConfig:
    data = await load_all(session)
    return ShopConfig(
        shop_name=data.get("shop_name", "Online Shopping"),
        support_username=data.get("support_username", ""),
        delivery_fee=_to_int(data.get("delivery_fee"), 0),
        free_delivery_from=_to_int(data.get("free_delivery_from"), 0),
        card_number=data.get("card_number", ""),
        card_holder=data.get("card_holder", ""),
    )


def _to_int(raw: str | None, fallback: int) -> int:
    try:
        return int(str(raw).replace(" ", "").replace(",", ""))
    except (TypeError, ValueError):
        return fallback


@dataclass(frozen=True, slots=True)
class SettingField:
    key: str
    label: str
    kind: Literal["text", "int", "username", "long"]
    hint: str = ""


SETTING_FIELDS: tuple[SettingField, ...] = (
    SettingField("shop_name", "🏪 Do'kon nomi", "text"),
    SettingField("support_username", "☎️ Yordam username (@siz)", "username"),
    SettingField("work_hours", "🕘 Ish vaqti", "text"),
    SettingField("delivery_fee", "🚚 Yetkazib berish narxi (so'm)", "int"),
    SettingField("free_delivery_from", "🎁 Bepul yetkazish summasi (so'm)", "int"),
    SettingField("card_number", "💳 Karta raqami", "text"),
    SettingField("card_holder", "👤 Karta egasi", "text"),
    SettingField("channel_url", "📣 Kanal havolasi", "text"),
    SettingField("welcome_text", "💬 Salomlashuv matni", "long"),
)

FIELD_BY_KEY = {field.key: field for field in SETTING_FIELDS}
