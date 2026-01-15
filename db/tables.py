# db/tables.py
import asyncpg
import logging
from .settings import SettingsRepo

# Настраиваем логгер (или используем loguru)
logger = logging.getLogger(__name__)


async def create_tables(pool: asyncpg.Pool):
    """
    Создает всю структуру базы данных.
    """
    logger.info("🚀 Начало инициализации таблиц БД...")

    async with pool.acquire() as conn:
        # 1. Users
        await conn.execute('''
                           CREATE TABLE IF NOT EXISTS users
                           (
                               user_id                 BIGINT PRIMARY KEY,
                               username                VARCHAR(50),
                               added_date_of_birth     DATE,
                               choice_tarot            TEXT      DEFAULT 'tarot_classic',
                               narrative_persona       TEXT DEFAULT 'default', -- Стиль общения (default, witch, cyberpunk, psychologist, etc.)
                               karma                   BIGINT    DEFAULT 50,
                               can_send_msg            BOOLEAN   DEFAULT true,
                               id_referrer             BIGINT    DEFAULT 0,
                               registration_date       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                               last_active_date        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                               premium_date            TIMESTAMP,
                               sub_my_freelancer_notes BOOLEAN   DEFAULT false
                           );
                           ''')

        # 2. Predicts
        await conn.execute('''
                           CREATE TABLE IF NOT EXISTS predicts
                           (
                               user_id                   BIGINT PRIMARY KEY REFERENCES users (user_id) ON DELETE CASCADE,
                               last_horoscope_daily_date DATE DEFAULT NULL,
                               last_tarot_daily_date     DATE DEFAULT NULL,
                               last_tarot_intro_date     DATE DEFAULT NULL,
                               last_tarot_date           DATE DEFAULT NULL
                           );
                           ''')

        # 3. ЮKassa Payments
        await conn.execute('''
                           CREATE TABLE IF NOT EXISTS payments_yookassa
                           (
                               id         BIGSERIAL PRIMARY KEY,
                               user_id    BIGINT      NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
                               amount     INTEGER     NOT NULL,
                               payload    TEXT        NOT NULL,
                               payment_id TEXT UNIQUE NOT NULL,
                               status     TEXT        DEFAULT 'pending',
                               created_at TIMESTAMPTZ DEFAULT NOW()
                           );
                           ''')

        # 4. Internal Payments (История операций кармы)
        await conn.execute('''
                           CREATE TABLE IF NOT EXISTS payments_internal
                           (
                               id             BIGSERIAL PRIMARY KEY,
                               user_id        BIGINT NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
                               type_operation TEXT,
                               amount         BIGINT,
                               created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                           );
                           ''')

        # 5. Settings
        await conn.execute("""
                           CREATE TABLE IF NOT EXISTS settings
                           (
                               setting_key          TEXT PRIMARY KEY,
                               setting_value        TEXT,
                               setting_display_name TEXT
                           );
                           """)

        # 6. Bot Images
        await conn.execute('''
                           CREATE TABLE IF NOT EXISTS bot_images
                           (
                               id         BIGSERIAL PRIMARY KEY,
                               dict_name  TEXT NOT NULL,
                               en         TEXT NOT NULL,
                               ru         TEXT NOT NULL,
                               arcana     TEXT,
                               image_path TEXT NOT NULL,
                               file_id    TEXT,
                               UNIQUE (dict_name, en)
                           );
                           ''')

        # 7. Daily Horoscope Cache
        await conn.execute('''
                           CREATE TABLE IF NOT EXISTS daily_horoscope
                           (
                               zodiac_sign    TEXT NOT NULL,
                               horoscope_date DATE NOT NULL,
                               content        TEXT NOT NULL,
                               generated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                               PRIMARY KEY (zodiac_sign, horoscope_date)
                           );
                           ''')

    # Инициализация дефолтных настроек
    settings_repo = SettingsRepo(pool)
    await settings_repo.initialize_defaults()

    logger.info("✅ Все таблицы успешно созданы и настроены.")