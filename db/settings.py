# db/settings.py
import asyncpg
from typing import Dict, Tuple, Optional

# Настройки по умолчанию (можно вынести в config, но тут тоже удобно)
DEFAULT_SETTINGS = {
    "price_daily_horoscope": ("5", "Цена ежедневного гороскопа"),
    "price_daily_tarot": ("0", "Цена ежедневной карты Таро"),
    "price_tarot_introduce": ("10", "Цена Знакомство с колодой"),
    "price_tarot_one_card": ("20", "Цена Таро-расклада Одиночная карта"),
    "price_tarot_ppf": ("50", "Цена Таро-расклада Пр-Наст-Буд"),
    "price_tarot_celtic_cross": ("150", "Цена Таро-расклада Кельтский крест"),
    "price_dreams": ("30", "Цена сонника"),
    "price_subscription": ("199", "Цена подписки (RUB)"),
    "price_karma_100": ("10", "Цена пакета 100 Кармы (RUB)"),
    "price_karma_500": ("40", "Цена пакета 500 Кармы (RUB)"),
    "price_karma_1000": ("70", "Цена пакета 1000 Кармы (RUB)"),
    "karma_welcome_bonus": ("50", "Приветственный бонус"),
    "karma_subscription_daily_bonus": ("50", "Ежедневный бонус по подписке"),
    "karma_channel_bonus": ("1", "Бонус за подписку на канал"),
}

class SettingsRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def initialize_defaults(self):
        """Записывает дефолтные настройки, если их нет."""
        sql = """
            INSERT INTO settings (setting_key, setting_value, setting_display_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (setting_key) DO NOTHING;
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for key, (val, name) in DEFAULT_SETTINGS.items():
                    await conn.execute(sql, key, val, name)

    async def get_all_settings(self) -> Dict[str, Dict[str, str]]:
        sql = "SELECT setting_key, setting_value, setting_display_name FROM settings;"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql)
            return {
                row["setting_key"]: {"value": row["setting_value"], "display_name": row["setting_display_name"]}
                for row in rows
            }

    async def get_setting(self, key: str) -> Optional[Dict[str, str]]:
        sql = "SELECT setting_value, setting_display_name FROM settings WHERE setting_key = $1;"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, key)
            if row:
                return {"value": row["setting_value"], "display_name": row["setting_display_name"]}
            return None

    async def update_setting(self, key: str, value: str, display_name: Optional[str] = None):
        sql = """
            INSERT INTO settings (setting_key, setting_value, setting_display_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (setting_key)
            DO UPDATE SET 
                setting_value = EXCLUDED.setting_value,
                setting_display_name = COALESCE(EXCLUDED.setting_display_name, settings.setting_display_name);
        """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, key, value, display_name)