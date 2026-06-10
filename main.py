import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from database.connection import init_db, init_connection, close_connection

# Routers
from handlers.root import router as root_router
from handlers.admin import router as admin_router
from handlers.public import router as public_router
from handlers.inline import router as inline_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    await init_connection()
    await init_db()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    dp.include_router(root_router)
    dp.include_router(admin_router)
    dp.include_router(public_router)
    dp.include_router(inline_router)
    
    from middlewares.throttling import ThrottlingMiddleware
    middleware = ThrottlingMiddleware(limit=2.5)
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)
    dp.inline_query.middleware(middleware)
    
    from database.models import get_setting, set_setting
    notify_id = await get_setting("restart_notify")
    if notify_id:
        try:
            await bot.send_message(chat_id=int(notify_id), text="✅ Бот успешно перезапущен и готов к работе!")
        except Exception as e:
            logger.error(f"Failed to send restart notification: {e}")
        await set_setting("restart_notify", "")
        
    logger.info("Starting bot polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await close_connection()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
