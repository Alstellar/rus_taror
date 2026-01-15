# db/bot_images.py
import asyncpg
from typing import Optional, List, Dict, Any


class ImageRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def insert_or_update_image(self, dict_name: str, en: str, ru: str, arcana: str, image_path: str,
                                     file_id: Optional[str] = None):
        """
        Добавляет или обновляет информацию о картинке.
        """
        sql = """
              INSERT INTO bot_images (dict_name, en, ru, arcana, image_path, file_id)
              VALUES ($1, $2, $3, $4, $5, $6)
              ON CONFLICT (dict_name, en)
                  DO UPDATE SET ru         = EXCLUDED.ru,
                                arcana     = EXCLUDED.arcana,
                                image_path = EXCLUDED.image_path,
                                file_id    = COALESCE(bot_images.file_id, EXCLUDED.file_id); \
              """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, dict_name, en, ru, arcana, image_path, file_id)

    async def update_file_id(self, record_id: int, new_file_id: str):
        """Обновляет file_id после успешной отправки в Telegram."""
        sql = "UPDATE bot_images SET file_id = $2 WHERE id = $1;"
        async with self.pool.acquire() as conn:
            await conn.execute(sql, record_id, new_file_id)

    async def get_random_cards(self, dict_name: str, count: int) -> List[asyncpg.Record]:
        """Возвращает случайные карты из указанной колоды."""
        sql = "SELECT * FROM bot_images WHERE dict_name = $1 ORDER BY random() LIMIT $2;"
        async with self.pool.acquire() as conn:
            return await conn.fetch(sql, dict_name, count)

    async def get_image_by_name(self, dict_name: str, en_name: str) -> Optional[asyncpg.Record]:
        """Ищет конкретную карту/схему по имени."""
        sql = "SELECT * FROM bot_images WHERE dict_name = $1 AND en = $2 LIMIT 1;"
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(sql, dict_name, en_name)

    async def get_image_without_file_id(self, dict_name: str) -> Optional[asyncpg.Record]:
        """Ищет картинку, у которой еще нет file_id (для технической загрузки)."""
        sql = "SELECT * FROM bot_images WHERE dict_name = $1 AND (file_id IS NULL OR file_id = '') LIMIT 1;"
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(sql, dict_name)

    async def get_unique_decks(self) -> List[str]:
        sql = "SELECT DISTINCT dict_name FROM bot_images;"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql)
            return [r['dict_name'] for r in rows]