# db/predicts.py
import asyncpg
from typing import Optional, Dict, Any


class PredictRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def add_predicts(self, user_id: int):
        """
        Создает запись в таблице predicts для нового пользователя.
        """
        sql = """
              INSERT INTO predicts (user_id)
              VALUES ($1)
              ON CONFLICT (user_id) DO NOTHING; \
              """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, user_id)

    async def get_predicts(self, user_id: int) -> Optional[asyncpg.Record]:
        """
        Получает данные о датах последних предсказаний.
        """
        sql = "SELECT * FROM predicts WHERE user_id = $1;"
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(sql, user_id)

    async def update_predicts(self, user_id: int, **kwargs: Any):
        """
        Обновляет даты предсказаний (например, last_horoscope_daily_date).
        """
        if not kwargs:
            return

        set_clause = ", ".join([f"{k} = ${i + 1}" for i, k in enumerate(kwargs.keys())])
        values = list(kwargs.values()) + [user_id]

        sql = f"""
            UPDATE predicts
            SET {set_clause}
            WHERE user_id = ${len(kwargs) + 1};
        """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, *values)