"""Demo ma'lumotlarni bazaga yuklaydi.

Ishlatish:
    python scripts/seed_demo.py

Skript idempotent: qayta ishga tushirilganda mavjud yozuvlarni takrorlamaydi.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

try:
    from bot.db import SessionFactory, dispose_db, init_db  # noqa: E402
    from bot.models import Category, Product  # noqa: E402
    from bot.services import promo as promo_service  # noqa: E402
    from bot.services import settings_store  # noqa: E402
except RuntimeError as exc:  # ConfigError ham shu yerga tushadi
    print(f"❌ Sozlamalar xato: {exc}")
    print("   .env faylini to'ldiring (.env.example dan nusxa oling).")
    raise SystemExit(1) from exc

CATEGORIES = [
    ("👕", "Kiyimlar", "Erkaklar va ayollar uchun mavsumiy kiyimlar"),
    ("👟", "Poyabzal", "Krossovka, tufli va sandallar"),
    ("📱", "Elektronika", "Telefonlar, aksessuarlar va gadjetlar"),
    ("🏠", "Uy uchun", "Idish-tovoq, to'qimachilik va uy jihozlari"),
]

PRODUCTS = [
    {
        "category": "Kiyimlar",
        "title": "Paxta ko'ylak Premium",
        "description": "100% paxta, yumshoq mato. Har kuni kiyish uchun qulay.",
        "price": 189_000,
        "old_price": 249_000,
        "stock": 25,
    },
    {
        "category": "Kiyimlar",
        "title": "Klassik jinsi shim",
        "description": "Straight fit, elastik mato. 5 ta o'lcham mavjud.",
        "price": 329_000,
        "old_price": 399_000,
        "stock": 18,
    },
    {
        "category": "Kiyimlar",
        "title": "Sport futbolka",
        "description": "Nafas oluvchi mato, tez quriydi. Sport uchun ideal.",
        "price": 129_000,
        "old_price": None,
        "stock": 40,
    },
    {
        "category": "Poyabzal",
        "title": "Yugurish krossovkasi",
        "description": "Yengil taglik, amortizatsiya. Har kun yugurish uchun.",
        "price": 549_000,
        "old_price": 699_000,
        "stock": 12,
    },
    {
        "category": "Poyabzal",
        "title": "Teridan tikilgan tufli",
        "description": "Tabiiy teri, klassis uslub. Ofis va tantanalar uchun.",
        "price": 749_000,
        "old_price": None,
        "stock": 7,
    },
    {
        "category": "Elektronika",
        "title": "Simsiz quloqchin",
        "description": "Bluetooth 5.3, shovqinni pasaytirish, 24 soat batareya.",
        "price": 459_000,
        "old_price": 599_000,
        "stock": 30,
    },
    {
        "category": "Elektronika",
        "title": "Power bank 20 000 mAh",
        "description": "Tez quvvatlash (PD 22.5W), ikkita USB port.",
        "price": 279_000,
        "old_price": None,
        "stock": 22,
    },
    {
        "category": "Uy uchun",
        "title": "Paxta choyshab to'plami",
        "description": "2 kishilik, 4 qism. Yumshoq va gigiyenik mato.",
        "price": 389_000,
        "old_price": 449_000,
        "stock": 15,
    },
    {
        "category": "Uy uchun",
        "title": "Termos 1 litr",
        "description": "Zanglamaydigan po'lat, 12 soat issiq saqlaydi.",
        "price": 149_000,
        "old_price": None,
        "stock": 35,
    },
]


async def seed() -> None:
    await init_db()

    created_categories = 0
    created_products = 0

    async with SessionFactory() as session:
        category_ids: dict[str, int] = {}

        for emoji, title, description in CATEGORIES:
            category = (
                await session.execute(select(Category).where(Category.title == title))
            ).scalar_one_or_none()
            if category is None:
                category = Category(title=title, emoji=emoji, description=description)
                session.add(category)
                await session.flush()
                created_categories += 1
            category_ids[title] = category.id

        for item in PRODUCTS:
            exists = (
                await session.execute(
                    select(Product.id).where(Product.title == item["title"])
                )
            ).scalar_one_or_none()
            if exists is not None:
                continue
            session.add(
                Product(
                    category_id=category_ids[item["category"]],
                    title=item["title"],
                    description=item["description"],
                    price=item["price"],
                    old_price=item["old_price"],
                    stock=item["stock"],
                )
            )
            created_products += 1

        await settings_store.set_value(session, "shop_name", "Online Shopping")
        await settings_store.set_value(session, "work_hours", "09:00 – 21:00")
        await settings_store.set_value(session, "delivery_fee", "20000")
        await settings_store.set_value(session, "free_delivery_from", "500000")

        promo_exists = await promo_service.get_by_code(session, "DEMO10")
        promo_created = False
        if promo_exists is None:
            demo, error = await promo_service.create(
                session,
                code="DEMO10",
                kind="percent",
                value=10,
                min_total=200_000,
                max_uses=None,
                days=None,
            )
            promo_created = demo is not None and not error

        await session.commit()

    await dispose_db()

    print("✅ Demo ma'lumotlar tayyor:")
    print(f"   • Yangi kategoriyalar: {created_categories}")
    print(f"   • Yangi mahsulotlar:   {created_products}")
    print(f"   • DEMO10 promokodi:    {'yaratildi' if promo_created else 'allaqachon mavjud'}")
    print("\nEndi botni ishga tushiring: python run.py")


if __name__ == "__main__":
    asyncio.run(seed())
