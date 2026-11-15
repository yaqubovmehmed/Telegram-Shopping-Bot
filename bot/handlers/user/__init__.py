"""All customer facing routers in priority order."""

from aiogram import Router

from bot.handlers.user import cart, catalog, inline, orders, payments, profile, start, webapp

router = Router(name="user")

# Profile/common first so «❌ Bekor qilish» and «🏠 Asosiy menyu» always work.
router.include_router(profile.router)
router.include_router(start.router)
router.include_router(catalog.router)
router.include_router(cart.router)
router.include_router(orders.router)
router.include_router(payments.router)
router.include_router(webapp.router)
router.include_router(inline.router)
