# 🛍 Online Shopping — Telegram do'kon boti

To'liq ishlaydigan onlayn-do'kon boti: katalog, savat, buyurtma qabul qilish,
to'lov usullari, admin panel, promokodlar, statistika, obuna darvozasi va
Telegram Mini App.

UI tili — **o'zbekcha**. Valyuta — **so'm** (butun son).

---

## ✨ Imkoniyatlar

**Mijoz uchun**

- 🛍 Kategoriyalar bo'yicha katalog, qidiruv, sahifalash
- 📄 Mahsulot kartasi: narx, eski narx, ombor qoldig'i, tavsif, rasm
- 🛒 Savat: sonini ±, o'chirish, tozalash, real vaqtda jami hisob
- ❤️ Saqlanganlar (istaklar ro'yxati)
- 🚚 Yetkazib berish narxi va «bepul yetkazish» chegarasi
- 🎟 Promokodlar (foiz yoki fiksirlangan summa, limit, muddat)
- 🧾 4 qadamli buyurtma: ism → telefon → manzil → izoh
- 💳 To'lov: naqd, karta (chek yuborish), Telegram Stars
- 📦 Buyurtmalar tarixi va holatni kuzatish, bekor qilish
- 👤 Profil va referal havola (`ref_<tg_id>`)
- 📣 Majburiy kanalga obuna darvozasi
- 🚀 Mini App'da xarid qilish (WebApp)

**Admin uchun**

- 📊 Statistika: foydalanuvchilar, buyurtmalar, tushum, top mahsulotlar
- 📦 Buyurtmalar: filtrlar, holatni o'zgartirish, to'lovni qayd etish,
  Stars to'lovini qaytarish
- 🛍 Mahsulotlar: qo'shish, tahrirlash, sotuvdan olish, o'chirish
- 🗂 Kategoriyalar: qo'shish, yashirish, o'chirish
- 📢 Broadcast: matn/rasm/video/fayl, bloklaganlarni belgilash
- 🎟 Promokodlar: yaratish, faolsizlantirish, o'chirish
- ⚙️ Sozlamalar: do'kon nomi, yordam, ish vaqti, yetkazish, karta, kanal
- 🔔 Yangi buyurtma haqida adminlarga avtomatik xabar

---

## 🧰 Texnologiyalar

| Qism | Texnologiya |
| --- | --- |
| Bot | Python 3.11+, aiogram 3.x |
| DB | SQLAlchemy 2.0 (async) + SQLite (aiosqlite) |
| Mini App backend | aiohttp |
| Sozlamalar | python-dotenv |
| Vaqt zonalari | tzdata |

---

## 🚀 Tez boshlash

### 1. Virtual muhit va kutubxonalar

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. `.env` faylini tayyorlang

```powershell
Copy-Item .env.example .env
```

Keyin `.env` ni ochib, kamida quyidagilarni to'ldiring:

| Kalit | Majburiy | Tavsif |
| --- | --- | --- |
| `BOT_TOKEN` | ✅ | [@BotFather](https://t.me/BotFather) dan olingan token |
| `ADMIN_IDS` | ✅ | Admin Telegram ID lari, vergul bilan (`123456789,987654321`) |
| `DATABASE_URL` | — | Standart: `sqlite+aiosqlite:///data/shop.db` |
| `TIMEZONE` | — | Standart: `Asia/Tashkent` |
| `STARS_RATE` | — | 1 Telegram Star = necha so'm (standart `250`) |
| `REQUIRED_CHANNEL_ID` | — | Majburiy obuna kanali ID si (masalan `-1001234567890`) |
| `REQUIRED_CHANNEL_URL` | — | Shu kanalning havolasi |
| `SUPPORT_USERNAME` | — | Yordam uchun username (`@siz`) |
| `ADMIN_LOG_CHAT_ID` | — | Buyurtmalar haqida xabar ketadigan guruh ID si |
| `THROTTLE_LIMIT` / `THROTTLE_WINDOW` | — | Anti-flood: `8` so'rov / `2` sekund |
| `WEBAPP_URL`, `WEBAPP_ENABLED` | — | Mini App uchun HTTPS manzil |
| `USE_WEBHOOK`, `WEBHOOK_URL`, `WEBHOOK_SECRET` | — | Polling o'rniga webhook |

> ⚠️ `.env` **hech qachon** git ga qo'shilmaydi (`.gitignore` da). Tokenni
> kodga, skriptlarga yoki loglarga yozmang.

### 3. Demo ma'lumotlar (ixtiyoriy)

```powershell
python scripts/seed_demo.py
```

4 kategoriya, 9 mahsulot va `DEMO10` promokodi qo'shiladi. Skript idempotent —
qayta ishga tushirsangiz dublikat yaratmaydi.

### 4. Botni ishga tushirish

```powershell
python run.py
```

Polling rejimida ishlaydi. Birinchi ishga tushishda SQLite jadvallari
avtomatik yaratiladi va adminlarga «Bot ishga tushdi» xabari yuboriladi.

---

## 🛠 Admin panel

Admin `/admin` buyrug'ini yuboradi yoki «🛠 Admin panel» tugmasini bosadi.
Adminlar uchun qo'shimcha buyruqlar `BotCommandScopeChat` orqali o'rnatiladi.

| Bo'lim | Nima qilish mumkin |
| --- | --- |
| 📊 Statistika | Foydalanuvchilar, buyurtmalar, tushum, o'rtacha chek, top mahsulotlar |
| 📦 Buyurtmalar | Holat bo'yicha filtr, kartani ochish, holatni o'zgartirish |
| 🛍 Mahsulotlar | Yangi mahsulot (7 qadam), maydonlarni tahrirlash, sotuvdan olish |
| 🗂 Kategoriyalar | Emoji + nom bilan qo'shish, yashirish, o'chirish |
| 📢 Broadcast | Xabar yuborish, natija hisoboti, bloklaganlarni belgilash |
| 🎟 Promokodlar | Foiz/summa, min. summa, foydalanish limiti, muddat |
| ⚙️ Sozlamalar | Do'kon nomi, yordam, ish vaqti, yetkazish, karta, kanal havolasi |

Buyurtma holatlari: `new → confirmed → shipping → delivered`, shuningdek
`cancelled`. Bekor qilinganda mahsulot omborga qaytariladi.

---

## 💳 To'lov usullari

| Usul | Qanday ishlaydi |
| --- | --- |
| `cash` | Naqd — yetkazib berishda. To'lov `delivered` bo'lganda `paid` |
| `card` | Karta raqami ko'rsatiladi, mijoz chek rasmini yuboradi |
| `stars` | Telegram Stars invoice (`XTR`), `pre_checkout_query` tekshiriladi |

- Stars narxi: `total / STARS_RATE`, kamida 1 Star.
- Stars to'lovi faqat `successful_payment` kelgandan keyin `paid` bo'ladi.
- Admin Stars to'lovini `refund_star_payment` orqali qaytarishi mumkin.
- Karta raqami bo'sh bo'lsa, «Karta» tugmasi ko'rsatilmaydi.

---

## 🚀 Telegram Mini App

Mini App — `bot/webapp/static/` dagi katalog va checkout UI, backend
`bot/webapp/server.py` (aiohttp).

### Yoqish

1. HTTPS manzil oling (VPS domeni yoki tunnel).
2. `.env` ga yozing:

   ```env
   WEBAPP_URL=https://shop.example.com
   WEBAPP_ENABLED=true
   WEBAPP_HOST=127.0.0.1
   WEBAPP_PORT=8080
   ```

3. Botni qayta ishga tushiring — menyu tugmasi `MenuButtonWebApp` ga
   o'tadi va reply-klaviaturada «🚀 Mini App» paydo bo'ladi.

### Lokal test uchun tunnel

```powershell
# Cloudflare Tunnel misoli
cloudflared tunnel --url http://127.0.0.1:8080
```

Chiqqan `https://...trycloudflare.com` manzilini `WEBAPP_URL` ga qo'ying.

### API

| Route | Tavsif |
| --- | --- |
| `GET /` | Mini App HTML |
| `GET /static/*` | CSS / JS |
| `GET /api/catalog` | Kategoriyalar va mahsulotlar |
| `GET /api/photo/{id}` | Mahsulot rasmi (proxy) |
| `POST /api/order` | Buyurtma yaratish |

`POST /api/order` `initData` ni bot tokeni bilan HMAC-SHA256 orqali tekshiradi
(`WebAppData` kaliti), `auth_date` 24 soatdan eski bo'lsa rad etadi va har bir
foydalanuvchi uchun soatiga 10 ta buyurtma bilan cheklaydi.

> Mini App faqat **HTTPS** manzilda Telegram ichida ochiladi. `http://localhost`
> brauzerda ishlaydi, lekin Telegram WebView'da emas.

---

## 📣 Obuna darvozasi

`REQUIRED_CHANNEL_ID` va `REQUIRED_CHANNEL_URL` to'ldirilsa, botdan foydalanish
uchun kanalga obuna talab qilinadi.

- Holat 5 daqiqa keshlanadi.
- `chat_member` update orqali kesh darhol yangilanadi (bot kanalda admin
  bo'lishi va `allowed_updates` da `chat_member` bo'lishi kerak).
- Adminlar tekshiruvdan ozod.
- API xatosi bo'lsa foydalanuvchi bloklanmaydi.

---

## 🧪 Testlar

```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe tests\test_smoke.py      # 41 servis tekshiruvi
.\.venv\Scripts\python.exe tests\test_handlers.py   # 36 dispatcher simulatsiyasi
```

- `test_smoke.py` — katalog, savat, promokod, buyurtma, ombor, statistika,
  klaviaturalar, `initData` imzosi, API route'lar.
- `test_handlers.py` — haqiqiy `Update` obyektlarini `dp.feed_update` orqali
  yuborib, mijoz va admin oqimlarini, FSM va DB commit'ni tekshiradi.

Testlar alohida SQLite fayllarida (`data/smoke_test.db`, `data/handler_test.db`)
ishlaydi va Telegram tarmog'iga murojaat qilmaydi.

Kod uslubi (ixtiyoriy, `ruff` bilan):

```powershell
pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check bot tests run.py scripts
```

---

## 📁 Loyiha tuzilishi

```
bot/
  config.py            # .env yuklash va validatsiya
  db.py                # engine, session factory, init_db
  models.py            # User, Category, Product, CartItem, Order, ...
  states.py            # FSM holatlari
  utils.py             # pul, sana, telefon, sahifalash
  views.py             # xabarlarni render qilish
  main.py              # bootstrap, middleware, polling/webhook
  handlers/
    user/              # start, catalog, cart, orders, payments, profile, webapp
    admin/             # panel, orders, products, broadcast
    channel.py         # chat_member
  middlewares/         # db, user, throttling, subscription
  keyboards/           # user va admin klaviaturalar
  services/            # cart, catalog, orders, promo, settings, notify
  webapp/              # aiohttp Mini App + static UI
scripts/seed_demo.py   # demo ma'lumotlar
tests/                 # smoke + handler testlar
run.py                 # kirish nuqtasi
```

---

## 🔐 Xavfsizlik

- Barcha sirlar `.env` da; kodda token yo'q.
- Loglarda token faqat maskalangan holda (`123456789:******abcd`).
- Mini App `initData` imzosi va `auth_date` tekshiriladi.
- Webhook uchun `WEBHOOK_SECRET` ishlatiladi.
- Anti-flood middleware va Mini App uchun soatiga 10 buyurtma limiti.
- Ombor atomar `UPDATE ... WHERE stock >= qty` bilan himoyalangan — oversell
  bo'lmaydi.
- Admin handlerlari `IsAdmin` filtri bilan yopilgan.
- SQLite faylini (`data/`) va `.env` ni zaxiralang, lekin git ga qo'shmang.

---

## 🧯 Muammolar va yechimlar

| Muammo | Yechim |
| --- | --- |
| `BOT_TOKEN topilmadi` | `.env` yaratilganini va token to'ldirilganini tekshiring |
| `ADMIN_IDS bo'sh` | Kamida bitta Telegram ID kiriting |
| Windows'da `UnicodeEncodeError` | `$env:PYTHONIOENCODING="utf-8"` qo'ying |
| `ZoneInfoNotFoundError` | `pip install tzdata` |
| `MissingGreenlet` | Odatda async lazy-load; bu loyihada `lazy="selectin"` ishlatiladi |
| Bot javob bermayapti | Token to'g'riligini, internetni va boshqa instance ishlamayotganini tekshiring |
| Mini App ochilmayapti | `WEBAPP_URL` HTTPS va tashqaridan ochiq bo'lishi kerak |
| Stars tugmasi yo'q | `STARS_RATE` 0 dan katta bo'lsin |
| Karta tugmasi yo'q | Admin panel → ⚙️ Sozlamalar → karta raqamini kiriting |

---

## 📄 Litsenziya

Ichki foydalanish uchun. Savdo loyihangizga moslab o'zgartiring.
