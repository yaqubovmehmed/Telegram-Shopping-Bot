"""Entry point: ``python run.py``."""

import asyncio
import sys

try:
    from bot.main import main
except RuntimeError as exc:  # ConfigError: .env to'ldirilmagan
    print(f"❌ Sozlamalar xatosi: {exc}")
    print("   .env faylini .env.example dan nusxalab to'ldiring.")
    sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
