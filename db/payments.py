# db/payments.py
import asyncpg
from typing import Optional, Any, List, Dict

class PaymentRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    # --- ЮKassa (Внешние платежи) ---

    async def add_yookassa_payment(self, user_id: int, amount: int, payload: str, payment_id: str) -> int:
        """
        Создает новую транзакцию ЮKassa со статусом pending.
        """
        sql = """
            INSERT INTO payments_yookassa (user_id, amount, payload, payment_id)
            VALUES ($1, $2, $3, $4)
            RETURNING id;
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(sql, user_id, amount, payload, payment_id)

    async def update_yookassa_status(self, payment_id: str, new_status: str) -> bool:
        """
        Обновляет статус платежа (succeeded/canceled).
        """
        sql = """
            UPDATE payments_yookassa
            SET status = $2
            WHERE payment_id = $1 AND status != $2
            RETURNING id;
        """
        async with self.pool.acquire() as conn:
            res = await conn.fetchval(sql, payment_id, new_status)
            return res is not None

    async def get_yookassa_payment(self, payment_id: str) -> Optional[asyncpg.Record]:
        sql = "SELECT * FROM payments_yookassa WHERE payment_id = $1;"
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(sql, payment_id)

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