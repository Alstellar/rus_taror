# db/users.py
import asyncpg
from typing import Optional, Any, List


class UserRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def add_user(self, user_id: int, username: Optional[str] = None, id_referrer: int = 0):
        """
        Добавляет нового пользователя.
        """
        sql = """
              INSERT INTO users (user_id, username, id_referrer)
              VALUES ($1, $2, $3)
              ON CONFLICT (user_id) DO NOTHING; \
              """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, user_id, username, id_referrer)

    async def get_user(self, user_id: int) -> Optional[asyncpg.Record]:
        """Получает профиль пользователя."""
        sql = "SELECT * FROM users WHERE user_id = $1;"
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(sql, user_id)

    async def update_user(self, user_id: int, **kwargs: Any):
        """Динамическое обновление полей пользователя."""
        if not kwargs:
            return

        set_clause = ", ".join([f"{k} = ${i + 1}" for i, k in enumerate(kwargs.keys())])
        values = list(kwargs.values()) + [user_id]

        sql = f"""
            UPDATE users
            SET {set_clause}
            WHERE user_id = ${len(kwargs) + 1};
        """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, *values)

    async def set_ban_status(self, user_id: int, is_ban: bool) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET is_ban = $2, can_send_msg = $3 WHERE user_id = $1;",
                user_id,
                is_ban,
                not is_ban,
            )

    async def get_all_user_ids(self, include_banned: bool = False) -> List[int]:
        sql = "SELECT user_id FROM users"
        if not include_banned:
            sql += " WHERE COALESCE(is_ban, false) = false"
        sql += ";"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql)
            return [row['user_id'] for row in rows]
