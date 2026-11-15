"""Order creation, lifecycle and statistics."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Order, OrderItem, Product, PromoCode, User
from bot.services import promo as promo_service
from bot.services.settings_store import ShopConfig
from bot.utils import day_start_utc, now_utc, order_code

ACTIVE_STATUSES = ("new", "confirmed", "shipping")
STATUSES = ("new", "confirmed", "shipping", "delivered", "cancelled")

PAYMENT_METHODS = ("cash", "card", "stars")


@dataclass(slots=True)
class CheckoutData:
    contact_name: str
    phone: str
    address: str
    comment: str = ""
    payment_method: str = "cash"
    promo_code: str | None = None


@dataclass(slots=True)
class CreateResult:
    order: Order | None = None
    error: str | None = None


async def create_order(
    session: AsyncSession,
    user: User,
    lines: list[tuple[Product, int]],
    data: CheckoutData,
    shop: ShopConfig,
) -> CreateResult:
    if not lines:
        return CreateResult(error="Savat bo'sh.")
    if data.payment_method not in PAYMENT_METHODS:
        return CreateResult(error="To'lov usuli noto'g'ri.")

    subtotal = 0
    for product, quantity in lines:
        if quantity <= 0:
            return CreateResult(error="Mahsulot soni noto'g'ri.")
        if not product.is_active:
            return CreateResult(error=f"«{product.title}» sotuvdan olingan.")
        if product.stock < quantity:
            return CreateResult(
                error=f"«{product.title}» omborda faqat {product.stock} dona qoldi."
            )
        subtotal += product.price * quantity

    discount = 0
    applied_promo: PromoCode | None = None
    if data.promo_code:
        check = await promo_service.check(session, data.promo_code, subtotal, lock=True)
        if not check.ok:
            return CreateResult(error=check.error)
        discount = check.discount
        applied_promo = check.promo

    payable = max(0, subtotal - discount)
    delivery_fee = 0
    if payable > 0 and shop.delivery_fee > 0:
        if not (shop.free_delivery_from > 0 and payable >= shop.free_delivery_from):
            delivery_fee = shop.delivery_fee
    total = payable + delivery_fee

    # Atomic stock reservation: never oversell, even with parallel checkouts.
    for product, quantity in lines:
        result = await session.execute(
            update(Product)
            .where(
                Product.id == product.id,
                Product.is_active.is_(True),
                Product.stock >= quantity,
            )
            .values(stock=Product.stock - quantity, sales_count=Product.sales_count + quantity)
        )
        if result.rowcount != 1:
            await session.rollback()
            return CreateResult(
                error="Ombordagi miqdor o'zgardi. Savatni yangilab, qaytadan urinib ko'ring."
            )

    if applied_promo is not None:
        result = await session.execute(
            update(PromoCode)
            .where(
                PromoCode.id == applied_promo.id,
                (PromoCode.max_uses.is_(None))
                | (PromoCode.used_count < PromoCode.max_uses),
            )
            .values(used_count=PromoCode.used_count + 1)
        )
        if result.rowcount != 1:
            await session.rollback()
            return CreateResult(error="Promokod limiti tugadi.")

    code = await _unique_code(session)
    order = Order(
        code=code,
        user=user,
        status="new",
        subtotal=subtotal,
        discount=discount,
        delivery_fee=delivery_fee,
        total=total,
        payment_method=data.payment_method,
        payment_status="pending",
        promo_code=applied_promo.code if applied_promo else None,
        contact_name=data.contact_name[:120],
        phone=data.phone[:32],
        address=data.address[:500],
        comment=(data.comment or None),
    )
    order.items = [
        OrderItem(
            product_id=product.id,
            title=product.title,
            price=product.price,
            quantity=quantity,
        )
        for product, quantity in lines
    ]
    session.add(order)
    await session.flush()
    return CreateResult(order=order)


async def _unique_code(session: AsyncSession) -> str:
    for _ in range(8):
        code = order_code()
        exists = await session.scalar(select(Order.id).where(Order.code == code))
        if not exists:
            return code
    return order_code() + "X"


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    return await session.get(Order, order_id)


async def get_by_code(session: AsyncSession, code: str) -> Order | None:
    return await session.scalar(select(Order).where(Order.code == code.strip().upper()))


async def user_orders(session: AsyncSession, user_id: int, limit: int = 20) -> list[Order]:
    stmt = (
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.id.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def admin_orders(
    session: AsyncSession, *, status: str | None = None, page: int = 1, per_page: int = 5
) -> tuple[list[Order], int, int]:
    conditions = []
    if status and status in STATUSES:
        conditions.append(Order.status == status)
    total = int(await session.scalar(select(func.count(Order.id)).where(*conditions)) or 0)
    total_pages = max(1, math.ceil(total / per_page))
    page = min(max(1, page), total_pages)
    stmt = (
        select(Order)
        .where(*conditions)
        .order_by(Order.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    orders = list((await session.execute(stmt)).scalars().all())
    return orders, total, total_pages


async def set_status(session: AsyncSession, order: Order, status: str) -> str | None:
    if status not in STATUSES:
        return "Noto'g'ri status."
    if order.status == status:
        return None
    if order.status == "cancelled":
        return "Bekor qilingan buyurtmani o'zgartirib bo'lmaydi."
    if status == "cancelled":
        for item in order.items:
            if item.product_id:
                await session.execute(
                    update(Product)
                    .where(Product.id == item.product_id)
                    .values(
                        stock=Product.stock + item.quantity,
                        sales_count=func.max(Product.sales_count - item.quantity, 0),
                    )
                )
    order.status = status
    order.updated_at = now_utc()
    if status == "delivered" and order.payment_method == "cash":
        order.payment_status = "paid"
    await session.flush()
    return None


async def mark_paid(session: AsyncSession, order: Order, charge_id: str | None = None) -> None:
    order.payment_status = "paid"
    if charge_id:
        order.charge_id = charge_id
    if order.status == "new":
        order.status = "confirmed"
    order.updated_at = now_utc()
    await session.flush()


async def mark_refunded(session: AsyncSession, order: Order) -> None:
    order.payment_status = "refunded"
    order.updated_at = now_utc()
    await session.flush()


async def cancel_new_order(session: AsyncSession, order: Order) -> str | None:
    if order.status not in ("new", "confirmed"):
        return "Buyurtma allaqachon yo'lda. Operator bilan bog'laning."
    return await set_status(session, order, "cancelled")


@dataclass(slots=True)
class ShopStats:
    users_total: int = 0
    users_today: int = 0
    orders_total: int = 0
    orders_today: int = 0
    active_orders: int = 0
    delivered_orders: int = 0
    cancelled_orders: int = 0
    revenue: int = 0
    paid_online: int = 0
    avg_check: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    top_products: list[tuple[str, int]] = field(default_factory=list)


@dataclass(slots=True)
class Preview:
    lines: list[tuple[Product, int]] = field(default_factory=list)
    subtotal: int = 0
    discount: int = 0
    delivery_fee: int = 0
    total: int = 0
    promo_error: str | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def units(self) -> int:
        return sum(quantity for _, quantity in self.lines)


async def preview(
    session: AsyncSession,
    items: list[tuple[int, int]],
    shop: ShopConfig,
    promo_code: str | None = None,
) -> Preview:
    """Recompute a checkout from ``(product_id, quantity)`` snapshots."""
    result = Preview()
    for product_id, quantity in items:
        product = await session.get(Product, product_id)
        if product is None or not product.is_active:
            result.problems.append("Ba'zi mahsulotlar sotuvdan olingan")
            continue
        result.lines.append((product, max(1, quantity)))
        result.subtotal += product.price * max(1, quantity)
        if product.stock < quantity:
            result.problems.append(f"«{product.title}»: omborda {product.stock} dona")

    if promo_code:
        check = await promo_service.check(session, promo_code, result.subtotal)
        if check.ok:
            result.discount = check.discount
        else:
            result.promo_error = check.error

    payable = max(0, result.subtotal - result.discount)
    if payable > 0 and shop.delivery_fee > 0:
        if not (shop.free_delivery_from > 0 and payable >= shop.free_delivery_from):
            result.delivery_fee = shop.delivery_fee
    result.total = payable + result.delivery_fee
    return result


async def shop_stats(session: AsyncSession) -> ShopStats:
    stats = ShopStats()
    stats.users_total = int(await session.scalar(select(func.count(User.id))) or 0)
    stats.users_today = int(
        await session.scalar(select(func.count(User.id)).where(User.created_at >= day_start_utc()))
        or 0
    )
    stats.orders_total = int(await session.scalar(select(func.count(Order.id))) or 0)
    stats.orders_today = int(
        await session.scalar(select(func.count(Order.id)).where(Order.created_at >= day_start_utc()))
        or 0
    )
    stats.active_orders = int(
        await session.scalar(
            select(func.count(Order.id)).where(Order.status.in_(ACTIVE_STATUSES))
        )
        or 0
    )
    stats.delivered_orders = int(
        await session.scalar(select(func.count(Order.id)).where(Order.status == "delivered")) or 0
    )
    stats.cancelled_orders = int(
        await session.scalar(select(func.count(Order.id)).where(Order.status == "cancelled")) or 0
    )
    stats.revenue = int(
        await session.scalar(
            select(func.coalesce(func.sum(Order.total), 0)).where(Order.status == "delivered")
        )
        or 0
    )
    stats.paid_online = int(
        await session.scalar(
            select(func.coalesce(func.sum(Order.total), 0)).where(Order.payment_status == "paid")
        )
        or 0
    )
    if stats.delivered_orders:
        stats.avg_check = stats.revenue // stats.delivered_orders

    rows = (
        await session.execute(
            select(Order.status, func.count(Order.id)).group_by(Order.status)
        )
    ).all()
    stats.status_counts = {status: count for status, count in rows}

    top = (
        await session.execute(
            select(Product.title, Product.sales_count)
            .where(Product.sales_count > 0)
            .order_by(Product.sales_count.desc())
            .limit(5)
        )
    ).all()
    stats.top_products = [(title, sold) for title, sold in top]
    return stats
