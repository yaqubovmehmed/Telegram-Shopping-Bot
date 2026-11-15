"""Promo code validation and management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import PromoCode
from bot.utils import money, now_utc


@dataclass(slots=True)
class PromoCheck:
    promo: PromoCode | None = None
    discount: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.promo is not None and self.error is None


def calc_discount(promo: PromoCode, subtotal: int) -> int:
    if promo.kind == "percent":
        percent = max(0, min(90, promo.value))
        return subtotal * percent // 100
    return max(0, min(promo.value, subtotal))


async def check(
    session: AsyncSession, code: str, subtotal: int, *, lock: bool = False
) -> PromoCheck:
    code = (code or "").strip().upper()
    if not code:
        return PromoCheck(error="Promokod kiritilmadi.")

    stmt = select(PromoCode).where(func.upper(PromoCode.code) == code)
    if lock:
        stmt = stmt.with_for_update()
    promo = await session.scalar(stmt)
    if promo is None:
        return PromoCheck(error="Bunday promokod topilmadi.")
    if not promo.is_active:
        return PromoCheck(error="Bu promokod faol emas.")
    if promo.expires_at and promo.expires_at < now_utc():
        return PromoCheck(error="Promokod muddati tugagan.")
    if promo.max_uses is not None and promo.used_count >= promo.max_uses:
        return PromoCheck(error="Promokod limiti tugagan.")
    if subtotal < promo.min_total:
        return PromoCheck(
            error=f"Promokod {money(promo.min_total)} dan yuqori buyurtmalar uchun."
        )

    discount = calc_discount(promo, subtotal)
    if discount <= 0:
        return PromoCheck(error="Bu buyurtmaga promokod qo'llanmaydi.")
    return PromoCheck(promo=promo, discount=discount)


async def list_all(session: AsyncSession, limit: int = 30) -> list[PromoCode]:
    stmt = select(PromoCode).order_by(PromoCode.is_active.desc(), PromoCode.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def get(session: AsyncSession, promo_id: int) -> PromoCode | None:
    return await session.get(PromoCode, promo_id)


async def get_by_code(session: AsyncSession, code: str) -> PromoCode | None:
    return await session.scalar(
        select(PromoCode).where(func.upper(PromoCode.code) == (code or "").strip().upper())
    )


async def create(
    session: AsyncSession,
    *,
    code: str,
    kind: str,
    value: int,
    min_total: int = 0,
    max_uses: int | None = None,
    days: int | None = None,
) -> tuple[PromoCode | None, str]:
    code = (code or "").strip().upper()
    if not (3 <= len(code) <= 32) or not code.replace("-", "").replace("_", "").isalnum():
        return None, "Kod 3–32 belgidan iborat bo'lishi va faqat harf/raqam bo'lishi kerak."
    if await get_by_code(session, code):
        return None, "Bu kod allaqachon mavjud."
    if kind not in {"percent", "fixed"}:
        return None, "Chegirma turi noto'g'ri."
    if kind == "percent" and not 1 <= value <= 90:
        return None, "Foiz 1–90 oralig'ida bo'lishi kerak."
    if kind == "fixed" and value <= 0:
        return None, "Summa 0 dan katta bo'lishi kerak."

    expires_at = None
    if days:
        from datetime import timedelta

        expires_at = datetime.combine(datetime.now().date() + timedelta(days=days), datetime.min.time())

    promo = PromoCode(
        code=code,
        kind=kind,
        value=value,
        min_total=min_total,
        max_uses=max_uses,
        expires_at=expires_at,
    )
    session.add(promo)
    await session.flush()
    return promo, ""


def describe(promo: PromoCode) -> str:
    if promo.kind == "percent":
        value = f"−{promo.value}%"
    else:
        value = f"−{money(promo.value)}"
    parts = [f"<b>{promo.code}</b> — {value}"]
    if promo.min_total:
        parts.append(f"min: {money(promo.min_total)}")
    if promo.max_uses is not None:
        parts.append(f"ishlatilgan: {promo.used_count}/{promo.max_uses}")
    else:
        parts.append(f"ishlatilgan: {promo.used_count}")
    if promo.expires_at:
        parts.append(f"muddat: {promo.expires_at:%d.%m.%Y}")
    if not promo.is_active:
        parts.append("⛔️ nofaol")
    return " · ".join(parts)


async def deactivate(session: AsyncSession, promo: PromoCode) -> None:
    promo.is_active = not promo.is_active
