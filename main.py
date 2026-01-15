# main.py
import asyncio
import sys
import asyncpg
from loguru import logger

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN, DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
from db.tables import create_tables
from utils.logger import setup_logger

# Импорт роутеров
from handlers.start import start_router
from handlers.profile import profile_router
from handlers.admin import admin_router
from handlers.tarot_logic import tarot_router
from handlers.marketplace import marketplace_router
from handlers.base import base_router

# Импорт планировщика
from scheduler import setup_scheduler

setup_logger()

async def main():
    logger.info("🚀 Запуск инициализации бота...")

    # 1. БД
    logger.info(f"🔌 Подключение к БД {DB_HOST}:{DB_PORT}...")
    try:
        pool = await (asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            min_size=5,
            max_size=20
        ))
    except Exception as e:
        logger.critical(f"❌ Критическая ошибка подключения к БД: {e}")
        sys.exit(1)

    # 2. Таблицы
    await create_tables(pool)

    # 3. Бот
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Внедряем пул БД
    dp["db_pool"] = pool

    # 4. Регистрация роутеров

    dp.include_router(admin_router)
    dp.include_router(start_router)
    dp.include_router(base_router)
    dp.include_router(profile_router)
    dp.include_router(marketplace_router)
    dp.include_router(tarot_router)

    # 5. Планировщик
    scheduler = setup_scheduler(bot, pool)
    scheduler.start()
    logger.info("⏰ Планировщик запущен.")

    # 6. Запуск
    logger.info("✅ Бот готов к работе!")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка в работе бота: {e}")
    finally:
        logger.info("🛑 Остановка...")
        await pool.close()
        logger.info("👋 Пока!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass