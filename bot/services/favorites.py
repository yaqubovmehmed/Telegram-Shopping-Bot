"""Wishlist helpers."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Favorite, Product


async def is_favorite(session: AsyncSession, user_id: int, product_id: int) -> bool:
    found = await session.scalar(
        select(Favorite.id).where(
            Favorite.user_id == user_id, Favorite.product_id == product_id
        )
    )
    return found is not None


async def toggle(session: AsyncSession, user_id: int, product_id: int) -> bool:
    favorite = await session.scalar(
        select(Favorite).where(
            Favorite.user_id == user_id, Favorite.product_id == product_id
        )
    )
    if favorite is None:
        session.add(Favorite(user_id=user_id, product_id=product_id))
        await session.flush()
        return True
    await session.delete(favorite)
    await session.flush()
    return False


async def count(session: AsyncSession, user_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count(Favorite.id)).where(Favorite.user_id == user_id)
        )
        or 0
    )


async def page(
    session: AsyncSession, user_id: int, page: int = 1, per_page: int = 6
) -> tuple[list[Product], int]:
    total = int(
        await session.scalar(
            select(func.count(Favorite.id))
            .join(Product, Product.id == Favorite.product_id)
            .where(Favorite.user_id == user_id, Product.is_active.is_(True))
        )
        or 0
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), total_pages)
    stmt = (
        select(Product)
        .join(Favorite, Favorite.product_id == Product.id)
        .where(Favorite.user_id == user_id, Product.is_active.is_(True))
        .order_by(Favorite.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    products = list((await session.execute(stmt)).scalars().all())
    return products, total_pages
