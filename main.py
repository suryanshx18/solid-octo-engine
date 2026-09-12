import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from database import init_db
from handlers import router as all_handlers_router

logging.basicConfig(level=logging.INFO)


async def main():
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(all_handlers_router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
