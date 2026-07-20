# db/payments.py
import asyncpg
from typing import List, Optional

class PaymentRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    # --- ЮKassa (Внешние платежи) ---

    async def add_yookassa_payment(
        self,
        user_id: int,
        amount: int,
        payload: str,
        payment_id: str,
        confirmation_url: str,
    ) -> int:
        """
        Создает новую транзакцию ЮKassa со статусом pending.
        """
        sql = """
            INSERT INTO payments_yookassa (user_id, amount, payload, payment_id, confirmation_url)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id;
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(sql, user_id, amount, payload, payment_id, confirmation_url)

    async def update_yookassa_status(self, payment_id: str, new_status: str) -> bool:
        """
        Обновляет статус платежа (succeeded/canceled).
        """
        sql = """
            UPDATE payments_yookassa
            SET status = $2
            WHERE payment_id = $1 AND status NOT IN ('fulfilled', 'canceled', 'expired')
            RETURNING id;
        """
        async with self.pool.acquire() as conn:
            res = await conn.fetchval(sql, payment_id, new_status)
            return res is not None

    async def get_yookassa_payment(self, payment_id: str) -> Optional[asyncpg.Record]:
        sql = "SELECT * FROM payments_yookassa WHERE payment_id = $1;"
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(sql, payment_id)

    async def get_recent_active_payment(
        self, user_id: int, payload: str, minutes: int = 5
    ) -> Optional[asyncpg.Record]:
        sql = """
            SELECT * FROM payments_yookassa
            WHERE user_id = $1
              AND payload = $2
              AND status = 'pending'
              AND created_at >= NOW() - ($3::int * INTERVAL '1 minute')
            ORDER BY created_at DESC
            LIMIT 1;
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(sql, user_id, payload, minutes)

    async def count_active_payments(self, user_id: int, hours: int = 4) -> int:
        sql = """
            SELECT COUNT(*) FROM payments_yookassa
            WHERE user_id = $1
              AND status = 'pending'
              AND created_at >= NOW() - ($2::int * INTERVAL '1 hour');
        """
        async with self.pool.acquire() as conn:
            return int(await conn.fetchval(sql, user_id, hours))

    async def get_active_payments(self, hours: int = 4) -> List[asyncpg.Record]:
        sql = """
            SELECT * FROM payments_yookassa
            WHERE status = 'pending'
              AND created_at >= NOW() - ($1::int * INTERVAL '1 hour')
            ORDER BY created_at ASC;
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(sql, hours)

    async def expire_payment(self, payment_id: str) -> bool:
        return await self.update_yookassa_status(payment_id, "expired")

    # --- Внутренние платежи (Карма) ---

    async def add_internal_transaction(self, user_id: int, operation_type: str, amount: int) -> int:
        """
        Записывает внутреннюю операцию (трата кармы или начисление бонуса).
        amount: отрицательное число (трата) или положительное (начисление).
        operation_type: например 'daily_horoscope', 'bonus_daily'.
        """
        sql = """
            INSERT INTO payments_internal (user_id, type_operation, amount)
            VALUES ($1, $2, $3)
            RETURNING id;
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(sql, user_id, operation_type, amount)

    async def apply_karma_transaction(self, user_id: int, operation_type: str, amount: int) -> Optional[int]:
        """
        Атомарно применяет изменение кармы и пишет запись в payments_internal.
        Возвращает новый баланс кармы, либо None если списание невозможно (например, недостаточно кармы).
        """
        if amount == 0:
            return None

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if amount < 0:
                    # Защищаем от ухода баланса в минус при конкурентных запросах.
                    new_karma = await conn.fetchval(
                        """
                        UPDATE users
                        SET karma = karma + $2
                        WHERE user_id = $1
                          AND karma + $2 >= 0
                        RETURNING karma;
                        """,
                        user_id,
                        amount,
                    )
                else:
                    new_karma = await conn.fetchval(
                        """
                        UPDATE users
                        SET karma = karma + $2
                        WHERE user_id = $1
                        RETURNING karma;
                        """,
                        user_id,
                        amount,
                    )

                if new_karma is None:
                    return None

                await conn.execute(
                    """
                    INSERT INTO payments_internal (user_id, type_operation, amount)
                    VALUES ($1, $2, $3);
                    """,
                    user_id,
                    operation_type,
                    amount,
                )

                return int(new_karma)
