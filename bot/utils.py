"""Small formatting / parsing helpers shared by handlers."""

from __future__ import annotations

import html
import math
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence, TypeVar

from bot.config import settings

T = TypeVar("T")

PHONE_RE = re.compile(r"^\+?\d[\d\s\-()]{7,18}$")


def esc(value: object) -> str:
    """Escape user-provided text before putting it into HTML messages."""
    return html.escape(str(value if value is not None else ""), quote=False)


def money(amount: int | float | None) -> str:
    amount = int(amount or 0)
    return f"{amount:,}".replace(",", " ") + f" {settings.shop_currency}"


def short(value: str, limit: int = 60) -> str:
    value = " ".join(str(value).split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def parse_int(raw: str, *, minimum: int = 0, maximum: int = 100_000_000) -> int | None:
    """Parse '12 000', '12,000', '12.000' -> 12000."""
    cleaned = re.sub(r"[^\d]", "", raw or "")
    if not cleaned:
        return None
    value = int(cleaned)
    if value < minimum or value > maximum:
        return None
    return value


def valid_phone(raw: str) -> bool:
    raw = (raw or "").strip()
    if not PHONE_RE.match(raw):
        return False
    digits = re.sub(r"\D", "", raw)
    return 9 <= len(digits) <= 15


def normalize_phone(raw: str) -> str:
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    return "+" + digits if raw.startswith("+") else digits


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(settings.tz)


def fmt_dt(dt: datetime | None, pattern: str = "%d.%m.%Y %H:%M") -> str:
    local = to_local(dt)
    return local.strftime(pattern) if local else "—"


def day_start_utc(days_ago: int = 0) -> datetime:
    """UTC timestamp of local midnight N days ago."""
    local_now = datetime.now(settings.tz)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
    return local_start.astimezone(timezone.utc).replace(tzinfo=None)


def order_code() -> str:
    return secrets.token_hex(3).upper()


def stars_amount(total_uzs: int) -> int:
    rate = settings.stars_rate or 250
    return max(1, min(10_000, math.ceil(total_uzs / rate)))


def paginate(items: Sequence[T], page: int, per_page: int) -> tuple[list[T], int, int]:
    """Return (page_items, page, total_pages). Page is 1-based and clamped."""
    total_pages = max(1, math.ceil(len(items) / per_page))
    page = min(max(1, page), total_pages)
    start = (page - 1) * per_page
    return list(items[start : start + per_page]), page, total_pages


def chunked(items: Iterable[T], size: int) -> list[list[T]]:
    chunk: list[T] = []
    result: list[list[T]] = []
    for item in items:
        chunk.append(item)
        if len(chunk) == size:
            result.append(chunk)
            chunk = []
    if chunk:
        result.append(chunk)
    return result


def user_link(tg_id: int, name: str) -> str:
    return f'<a href="tg://user?id={tg_id}">{esc(name or tg_id)}</a>'


STATUS_LABELS = {
    "new": "🆕 Yangi",
    "confirmed": "✅ Tasdiqlangan",
    "shipping": "🚚 Yetkazilmoqda",
    "delivered": "📬 Yetkazilgan",
    "cancelled": "❌ Bekor qilingan",
}

PAYMENT_LABELS = {
    "cash": "💵 Naqd (yetkazib berishda)",
    "card": "💳 Karta orqali",
    "stars": "⭐ Telegram Stars",
}

PAYMENT_STATUS_LABELS = {
    "pending": "⏳ Kutilmoqda",
    "paid": "✅ To'langan",
    "refunded": "↩️ Qaytarilgan",
}


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def payment_label(method: str) -> str:
    return PAYMENT_LABELS.get(method, method)


def payment_status_label(status: str) -> str:
    return PAYMENT_STATUS_LABELS.get(status, status)
