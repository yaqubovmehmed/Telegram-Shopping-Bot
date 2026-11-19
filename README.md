# Telegram Shopping Bot

A full-featured online shop bot with a product catalog, cart, checkout, payment options, admin panel, promotions, analytics, subscription gate, and Telegram Mini App.

The customer interface is in **Uzbek**, and prices are displayed in **Uzbek so'm (UZS)**.

## Features

### For customers

- Browse categories, search and paginate through products
- View product prices, sale prices, stock, descriptions, and photos
- Add items to a cart, adjust quantities, and save favorites
- Apply percentage or fixed-amount promo codes
- Place orders with name, phone, address, and optional note
- Choose cash, card transfer with receipt, or Telegram Stars
- Track or cancel orders, view order history, and share referral links
- Use the Telegram Mini App to browse and order
- Optionally require membership in a Telegram channel

### For administrators

- View user, order, revenue, and top-product statistics
- Manage orders, statuses, and payment records
- Create, edit, hide, and remove products and categories
- Send broadcasts and manage promo codes
- Configure shop details, support, working hours, delivery, payment card, and channel
- Receive automatic new-order notifications
- Refund Telegram Stars payments

## Technology

| Component | Technology |
| --- | --- |
| Bot | Python 3.11+, aiogram 3.x |
| Database | SQLAlchemy 2.0 async + SQLite (aiosqlite) |
| Mini App backend | aiohttp |
| Configuration | python-dotenv |
| Time zones | tzdata |

## Quick start

### 1. Install dependencies

**Windows PowerShell**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Linux / macOS**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure the environment

Copy `.env.example` to `.env` and set at least:

| Variable | Required | Purpose |
| --- | --- | --- |
| `BOT_TOKEN` | Yes | Token from [@BotFather](https://t.me/BotFather) |
| `ADMIN_IDS` | Yes | Comma-separated Telegram admin IDs |
| `DATABASE_URL` | No | Defaults to `sqlite+aiosqlite:///data/shop.db` |
| `TIMEZONE` | No | Defaults to `Asia/Tashkent` |
| `STARS_RATE` | No | UZS per Telegram Star; defaults to `250` |
| `REQUIRED_CHANNEL_ID`, `REQUIRED_CHANNEL_URL` | No | Optional membership gate |
| `SUPPORT_USERNAME` | No | Support contact username |
| `ADMIN_LOG_CHAT_ID` | No | Chat for order notifications |
| `WEBAPP_URL`, `WEBAPP_ENABLED` | No | HTTPS URL and Mini App switch |
| `USE_WEBHOOK`, `WEBHOOK_URL`, `WEBHOOK_SECRET` | No | Optional webhook mode |

Never commit `.env`, bot tokens, or other credentials. Keep secrets out of source code and logs.

### 3. Optional demo data

```bash
python scripts/seed_demo.py
```

This adds four categories, nine products, and the `DEMO10` promo code. The seed script is idempotent.

### 4. Start the bot

```bash
python run.py
```

The bot starts in polling mode by default. On first start, it creates the SQLite tables and notifies administrators.

## Order and payment behavior

Order statuses are `new → confirmed → shipping → delivered`, with `cancelled` as an alternative. Cancelling an order returns its items to stock.

- **Cash:** payment is marked paid when the order is delivered.
- **Card:** the customer sees the configured card details and can send a receipt.
- **Telegram Stars:** checkout uses the `XTR` currency; an order is marked paid only after Telegram confirms successful payment. Administrators can issue a Stars refund.

## Telegram Mini App

The Mini App serves its UI from `bot/webapp/static/`; the aiohttp server is in `bot/webapp/server.py`.

To enable it, set an externally reachable HTTPS URL in `.env`:

```env
WEBAPP_URL=https://shop.example.com
WEBAPP_ENABLED=true
WEBAPP_HOST=127.0.0.1
WEBAPP_PORT=8080
```

Then restart the bot. For a temporary local tunnel, you can use:

```bash
cloudflared tunnel --url http://127.0.0.1:8080
```

The API includes `GET /`, `GET /static/*`, `GET /api/catalog`, `GET /api/photo/{id}`, and `POST /api/order`. The order endpoint validates Telegram `initData`, rejects data older than 24 hours, and limits each user to ten orders per hour.

## Tests

Run the offline checks without a Telegram token:

```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe tests\test_smoke.py
.\.venv\Scripts\python.exe tests\test_handlers.py
```

The smoke suite covers services and API routes; the handler suite simulates user and admin flows with isolated SQLite databases.

## Security notes

- Keep `.env`, database files, and secrets out of Git.
- Mini App requests validate Telegram `initData` and `auth_date`.
- Webhook mode supports a `WEBHOOK_SECRET`.
- Admin actions are protected by role checks; requests are rate-limited.
- Stock updates guard against selling more items than are available.

## License

This project is available under the [MIT License](LICENSE).
