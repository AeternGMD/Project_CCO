import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from database.connection import init_db

# Routers
from handlers.root import router as root_router
from handlers.admin import router as admin_router
from handlers.public import router as public_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    await init_db()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    dp.include_router(root_router)
    dp.include_router(admin_router)
    dp.include_router(public_router)
    
    logger.info("Starting bot polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
