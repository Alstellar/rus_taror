# db/daily_horoscope.py
import asyncpg
from datetime import date
from typing import Optional

class HoroscopeRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def add_horoscope(self, zodiac_sign: str, horoscope_date: date, content: str):
        """
        Сохраняет сгенерированный гороскоп.
        """
        sql = """
            INSERT INTO daily_horoscope (zodiac_sign, horoscope_date, content)
            VALUES ($1, $2, $3)
            ON CONFLICT (zodiac_sign, horoscope_date) 
            DO UPDATE SET content = $3, generated_at = CURRENT_TIMESTAMP;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, zodiac_sign, horoscope_date, content)

    async def get_horoscope(self, zodiac_sign: str, horoscope_date: date) -> Optional[asyncpg.Record]:
        """
        Достает гороскоп из кэша.
        """
        sql = """
            SELECT * FROM daily_horoscope
            WHERE zodiac_sign = $1 AND horoscope_date = $2;
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(sql, zodiac_sign, horoscope_date)