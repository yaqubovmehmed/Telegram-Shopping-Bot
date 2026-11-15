"""Environment based configuration.

Every secret (bot token, admin ids, web-app settings) lives in ``.env``.
Nothing sensitive is ever written into the source tree or into logs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)


class ConfigError(RuntimeError):
    """Raised when the environment is not usable."""


def _int(name: str, default: int | None = None) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} butun son bo'lishi kerak, hozir: {raw!r}") from exc


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} son bo'lishi kerak, hozir: {raw!r}") from exc


def _ids(name: str) -> tuple[int, ...]:
    raw = os.getenv(name, "").replace(";", ",")
    result: list[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            result.append(int(chunk))
        except ValueError as exc:
            raise ConfigError(f"{name} ichida noto'g'ri ID bor: {chunk!r}") from exc
    return tuple(dict.fromkeys(result))


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "ha"}


def _text(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    admin_ids: tuple[int, ...]
    admin_log_chat_id: int | None
    database_url: str
    timezone: str
    shop_currency: str
    stars_rate: float
    webapp_url: str
    webapp_host: str
    webapp_port: int
    webapp_enabled: bool
    required_channel_id: int | None
    required_channel_url: str
    support_username: str
    throttle_limit: int
    throttle_window: float
    use_webhook: bool
    webhook_url: str
    webhook_path: str
    webhook_secret: str
    log_level: str
    tz: ZoneInfo = field(init=False)

    def __post_init__(self) -> None:
        try:
            tz = ZoneInfo(self.timezone)
        except Exception:
            tz = ZoneInfo("UTC")
        object.__setattr__(self, "tz", tz)

    @property
    def masked_token(self) -> str:
        """Safe representation of the token for logs / diagnostics."""
        token = self.bot_token
        if not token:
            return "<not set>"
        if ":" not in token:
            return "***"
        head, tail = token.split(":", 1)
        return f"{head}:{'*' * 6}{tail[-4:]}"

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and ":" in self.bot_token and self.admin_ids)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


def load_settings() -> Settings:
    token = _text("BOT_TOKEN")
    admins = _ids("ADMIN_IDS")

    webapp_url = _text("WEBAPP_URL").rstrip("/")
    webapp_port = _int("WEBAPP_PORT", 8080) or 8080
    webapp_enabled = _bool("WEBAPP_ENABLED", bool(webapp_url))

    settings = Settings(
        bot_token=token,
        admin_ids=admins,
        admin_log_chat_id=_int("ADMIN_LOG_CHAT_ID"),
        database_url=_text("DATABASE_URL", "sqlite+aiosqlite:///data/shop.db"),
        timezone=_text("TIMEZONE", "Asia/Tashkent"),
        shop_currency=_text("SHOP_CURRENCY", "so'm"),
        stars_rate=_float("STARS_RATE", 250.0),
        webapp_url=webapp_url,
        webapp_host=_text("WEBAPP_HOST", "127.0.0.1"),
        webapp_port=webapp_port,
        webapp_enabled=webapp_enabled,
        required_channel_id=_int("REQUIRED_CHANNEL_ID"),
        required_channel_url=_text("REQUIRED_CHANNEL_URL"),
        support_username=_text("SUPPORT_USERNAME"),
        throttle_limit=max(1, _int("THROTTLE_LIMIT", 8) or 8),
        throttle_window=max(0.5, _float("THROTTLE_WINDOW", 2.0)),
        use_webhook=_bool("USE_WEBHOOK", False),
        webhook_url=_text("WEBHOOK_URL").rstrip("/"),
        webhook_path=_text("WEBHOOK_PATH", "/telegram/webhook"),
        webhook_secret=_text("WEBHOOK_SECRET"),
        log_level=_text("LOG_LEVEL", "INFO").upper(),
    )

    if not token:
        raise ConfigError(
            "BOT_TOKEN topilmadi. .env faylini .env.example dan nusxalab, "
            "@BotFather dan olingan tokenni kiriting."
        )
    if not admins:
        raise ConfigError("ADMIN_IDS bo'sh. Kamida bitta Telegram ID kiriting.")
    if not settings.stars_rate > 0:
        raise ConfigError("STARS_RATE 0 dan katta bo'lishi kerak.")
    if settings.use_webhook and (not settings.webhook_url or not settings.webhook_secret):
        raise ConfigError("USE_WEBHOOK=true bo'lsa WEBHOOK_URL va WEBHOOK_SECRET majburiy.")
    return settings


settings = load_settings()
