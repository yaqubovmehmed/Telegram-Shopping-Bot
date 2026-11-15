"""Admin router: every handler is protected by :class:`IsAdmin`."""

from aiogram import Router

from bot.filters.admin import IsAdmin
from bot.handlers.admin import broadcast, orders, panel, products

router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

router.include_router(panel.router)
router.include_router(orders.router)
router.include_router(products.router)
router.include_router(broadcast.router)
