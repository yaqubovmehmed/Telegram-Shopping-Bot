"""User lookup / profile helpers."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import User


async def get_or_create(
    session: AsyncSession,
    tg_id: int,
    *,
    username: str | None = None,
    full_name: str = "",
    referral_id: int | None = None,
) -> tuple[User, bool]:
    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if user is not None:
        return user, False

    if referral_id in {None, tg_id}:
        referral_id = None
    else:
        exists = await session.scalar(select(User.id).where(User.tg_id == referral_id))
        if exists is None:
            referral_id = None

    user = User(
        tg_id=tg_id,
        username=username,
        full_name=full_name or "Foydalanuvchi",
        referral_id=referral_id,
    )
    session.add(user)
    await session.flush()
    return user, True


async def count(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count(User.id))) or 0)


async def all_ids(session: AsyncSession, *, include_blocked: bool = False) -> list[int]:
    stmt = select(User.tg_id)
    if not include_blocked:
        stmt = stmt.where(User.is_blocked.is_(False))
    return list((await session.execute(stmt)).scalars().all())
