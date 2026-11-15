"""Catalog queries: categories, products, search."""

from __future__ import annotations

import math

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Category, Product

PRODUCTS_PER_PAGE = 6


async def list_categories(session: AsyncSession, *, active_only: bool = True) -> list[Category]:
    stmt = select(Category)
    if active_only:
        stmt = stmt.where(Category.is_active.is_(True))
    stmt = stmt.order_by(Category.sort_order, Category.id)
    return list((await session.execute(stmt)).scalars().all())


async def get_category(session: AsyncSession, category_id: int) -> Category | None:
    return await session.get(Category, category_id)


async def category_counts(session: AsyncSession) -> dict[int, int]:
    stmt = (
        select(Product.category_id, func.count(Product.id))
        .where(Product.is_active.is_(True), Product.stock > 0)
        .group_by(Product.category_id)
    )
    return {row[0]: row[1] for row in (await session.execute(stmt)).all() if row[0] is not None}


async def products_page(
    session: AsyncSession,
    *,
    category_id: int | None = None,
    page: int = 1,
    per_page: int = PRODUCTS_PER_PAGE,
    search: str | None = None,
    active_only: bool = True,
    in_stock_only: bool = False,
) -> tuple[list[Product], int, int]:
    conditions = []
    if active_only:
        conditions.append(Product.is_active.is_(True))
    if in_stock_only:
        conditions.append(Product.stock > 0)
    if category_id is not None:
        conditions.append(Product.category_id == category_id)
    if search:
        needle = search.strip()
        if needle:
            conditions.append(
                or_(Product.title.ilike(f"%{needle}%"), Product.description.ilike(f"%{needle}%"))
            )

    total = int(
        await session.scalar(select(func.count(Product.id)).where(*conditions)) or 0
    )
    total_pages = max(1, math.ceil(total / per_page))
    page = min(max(1, page), total_pages)

    stmt = (
        select(Product)
        .where(*conditions)
        .order_by(Product.is_active.desc(), Product.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    products = list((await session.execute(stmt)).scalars().all())
    return products, total, total_pages


async def get_product(session: AsyncSession, product_id: int) -> Product | None:
    return await session.get(Product, product_id)


async def top_products(session: AsyncSession, limit: int = 5) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.sales_count > 0)
        .order_by(Product.sales_count.desc(), Product.id.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def in_stock_count(session: AsyncSession) -> int:
    return int(
        await session.scalar(
            select(func.count(Product.id)).where(Product.is_active.is_(True), Product.stock > 0)
        )
        or 0
    )
