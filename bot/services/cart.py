"""Shopping cart logic and totals."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import CartItem, Product
from bot.services.settings_store import ShopConfig


@dataclass(slots=True)
class CartSummary:
    subtotal: int = 0
    discount: int = 0
    delivery_fee: int = 0
    total: int = 0
    positions: int = 0
    units: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.positions == 0


def summarize(items: list[CartItem], shop: ShopConfig, *, discount: int = 0) -> CartSummary:
    summary = CartSummary()
    subtotal = 0
    for item in items:
        product = item.product
        if product is None or not product.is_active:
            summary.problems.append(f"«{product.title if product else 'Mahsulot'}» endi sotuvda yo'q")
            continue
        summary.positions += 1
        summary.units += item.quantity
        subtotal += product.price * item.quantity
        if product.stock < item.quantity:
            summary.problems.append(
                f"«{product.title}» omborda faqat {product.stock} dona qoldi"
            )

    summary.subtotal = subtotal
    summary.discount = max(0, min(discount, subtotal))
    payable = subtotal - summary.discount

    if payable > 0 and shop.delivery_fee > 0:
        if shop.free_delivery_from > 0 and payable >= shop.free_delivery_from:
            summary.delivery_fee = 0
        else:
            summary.delivery_fee = shop.delivery_fee

    summary.total = max(0, payable + summary.delivery_fee)
    return summary


async def get_items(session: AsyncSession, user_id: int) -> list[CartItem]:
    stmt = (
        select(CartItem)
        .where(CartItem.user_id == user_id)
        .order_by(CartItem.created_at, CartItem.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_item(session: AsyncSession, item_id: int, user_id: int) -> CartItem | None:
    return await session.scalar(
        select(CartItem).where(CartItem.id == item_id, CartItem.user_id == user_id)
    )


async def count_positions(session: AsyncSession, user_id: int) -> int:
    return int(
        await session.scalar(select(func.count(CartItem.id)).where(CartItem.user_id == user_id)) or 0
    )


async def add(
    session: AsyncSession, user_id: int, product_id: int, quantity: int = 1
) -> tuple[int, str]:
    """Add a product. Returns (added_quantity, message)."""
    product = await session.get(Product, product_id)
    if product is None or not product.is_active:
        return 0, "Mahsulot topilmadi yoki sotuvdan olingan."
    if product.stock <= 0:
        return 0, "Afsuski, bu mahsulot omborda qolmagan."

    item = await session.scalar(
        select(CartItem).where(CartItem.user_id == user_id, CartItem.product_id == product_id)
    )
    current = item.quantity if item else 0
    wanted = current + max(1, quantity)
    allowed = min(wanted, product.stock)

    if allowed <= current:
        return 0, f"Omborda faqat {product.stock} dona mavjud."

    if item is None:
        session.add(CartItem(user_id=user_id, product_id=product_id, quantity=allowed))
    else:
        item.quantity = allowed
    await session.flush()

    added = allowed - current
    if allowed < wanted:
        return added, f"{added} dona qo'shildi. Omborda jami {product.stock} dona bor."
    return added, f"«{product.title}» savatga qo'shildi ({allowed} dona)."


async def set_quantity(
    session: AsyncSession, item: CartItem, quantity: int
) -> tuple[bool, str]:
    product = item.product
    if product is None:
        await session.delete(item)
        return False, "Mahsulot topilmadi, savatdan olib tashlandi."
    if quantity <= 0:
        await session.delete(item)
        return True, "O'chirildi."
    if quantity > product.stock:
        return False, f"Omborda faqat {product.stock} dona mavjud."
    item.quantity = quantity
    return True, ""


async def remove(session: AsyncSession, item: CartItem) -> None:
    await session.delete(item)


async def clear(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(CartItem).where(CartItem.user_id == user_id))
