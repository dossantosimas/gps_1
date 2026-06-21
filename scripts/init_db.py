import asyncio

from db import close_database, init_database


async def main() -> None:
    pool = await init_database()
    try:
        print("[*] Tablas preparadas en la base de datos.")
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
