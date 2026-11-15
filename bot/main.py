"""Bot bootstrap: middlewares, routers, commands, polling / webhook."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    ErrorEvent,
    MenuButtonWebApp,
    WebAppInfo,
)

from bot import __version__
from bot.config import settings
from bot.db import SessionFactory, dispose_db, init_db
from bot.handlers import admin as admin_handlers
from bot.handlers import channel
from bot.handlers import user as user_handlers
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.middlewares.user import UserMiddleware

log = logging.getLogger("shopbot")

ALLOWED_UPDATES = [
    "message",
    "callback_query",
    "inline_query",
    "pre_checkout_query",
    "chat_member",
]


def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True,
        ),
    )


def create_dispatcher(bot: Bot) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    throttling = ThrottlingMiddleware()
    db_session = DbSessionMiddleware(SessionFactory)
    user_middleware = UserMiddleware()
    subscription = SubscriptionMiddleware(bot)

    for observer in (dp.message, dp.callback_query, dp.inline_query):
        observer.middleware(throttling)
        observer.middleware(db_session)
        observer.middleware(user_middleware)
        if observer is not dp.inline_query:
            observer.middleware(subscription)

    for observer in (dp.pre_checkout_query,):
        observer.middleware(db_session)
        observer.middleware(user_middleware)

    dp.include_router(admin_handlers.router)
    dp.include_router(user_handlers.router)
    dp.include_router(channel.router)

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        log.exception("Unhandled error while processing update", exc_info=event.exception)
        return True

    return dp


async def setup_commands(bot: Bot) -> None:
    user_commands = [
        BotCommand(command="start", description="🏠 Boshlash"),
        BotCommand(command="menu", description="📋 Asosiy menyu"),
        BotCommand(command="help", description="ℹ️ Yordam"),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    admin_commands = [
        *user_commands,
        BotCommand(command="admin", description="🛠 Admin panel"),
    ]
    for admin_id in settings.admin_ids:
        try:
            await bot.set_my_commands(
                admin_commands, scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except Exception:
            log.warning("Could not set admin commands for %s", admin_id)

    if settings.webapp_enabled and settings.webapp_url:
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="🛍 Do'kon", web_app=WebAppInfo(url=settings.webapp_url)
                )
            )
        except Exception:
            log.warning("Could not set the Mini App menu button")


async def notify_startup(bot: Bot) -> None:
    me = await bot.get_me()
    log.info("Bot started: @%s (Bot API)", me.username)
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f"✅ <b>Bot ishga tushdi</b>\n\n"
                f"🤖 @{me.username}\n"
                f"📦 Versiya: {__version__}\n"
                f"🔐 Token: <code>{settings.masked_token}</code>",
            )
        except Exception:
            pass


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def main() -> None:
    _configure_logging()
    log.info("Starting shop bot (config OK, admins: %d)", len(settings.admin_ids))

    await init_db()
    bot = create_bot()
    dp = create_dispatcher(bot)

    webapp_runner = None
    if settings.webapp_enabled and settings.webapp_url:
        from bot.webapp.server import start_webapp

        webapp_runner = await start_webapp(bot)
        log.info("Mini App server: http://%s:%s", settings.webapp_host, settings.webapp_port)

    try:
        await setup_commands(bot)
        await notify_startup(bot)

        if settings.use_webhook:
            await run_webhook(bot, dp)
        else:
            await dp.start_polling(
                bot,
                allowed_updates=ALLOWED_UPDATES,
                drop_pending_updates=False,
            )
    finally:
        if webapp_runner is not None:
            from bot.webapp.server import stop_webapp

            await stop_webapp(webapp_runner)
        await bot.session.close()
        await dispose_db()
        log.info("Bot stopped")


async def run_webhook(bot: Bot, dp: Dispatcher) -> None:
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    url = f"{settings.webhook_url}{settings.webhook_path}"
    await bot.set_webhook(
        url=url,
        secret_token=settings.webhook_secret,
        allowed_updates=ALLOWED_UPDATES,
        drop_pending_updates=False,
    )
    log.info("Webhook set: %s", url)

    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.webhook_secret,
    ).register(app, path=settings.webhook_path)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.webapp_host, settings.webapp_port)
    await site.start()
    log.info("Webhook server listening on %s:%s", settings.webapp_host, settings.webapp_port)

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await bot.delete_webhook()
