import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from aiogram import Bot
from loguru import logger
from yookassa import Configuration, Payment

from config import LOG_GROUP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_SHOP_ID
from db import PaymentRepo, SettingsRepo
from utils.sender import send_text

Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY


class YooKassaService:
    """Polling-based YooKassa processing, resilient to bot restarts."""

    _active_checks: set[str] = set()
    PAYMENT_WINDOW = timedelta(hours=4)

    def __init__(self, bot: Bot, pool):
        self.bot = bot
        self.pool = pool

    async def create_payment(self, amount: int, description: str, user_id: int) -> Tuple[str, str]:
        payment = await asyncio.to_thread(
            Payment.create,
            {
                "amount": {"value": f"{amount}.00", "currency": "RUB"},
                "confirmation": {
                    "type": "redirect",
                    "return_url": "https://t.me/rus_tarot_bot",
                },
                "capture": True,
                "description": description,
                "metadata": {"user_id": str(user_id)},
            },
            str(uuid.uuid4()),
        )
        return payment.confirmation.confirmation_url, payment.id

    async def resume_pending_checks(self) -> None:
        """Resume checks after startup and periodically discover missed in-memory tasks."""
        records = await PaymentRepo(self.pool).get_active_payments(hours=4)
        for record in records:
            self.start_check(dict(record))

    def start_check(self, record: dict) -> None:
        payment_id = record["payment_id"]
        if payment_id in self._active_checks:
            return
        self._active_checks.add(payment_id)
        asyncio.create_task(
            self.check_payment_loop(record, already_claimed=True),
            name=f"yookassa:{payment_id}",
        )

    @staticmethod
    def _as_aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    @staticmethod
    def _next_interval(elapsed: timedelta) -> int:
        if elapsed < timedelta(minutes=10):
            return 60
        if elapsed < timedelta(hours=1):
            return 300
        return 900

    async def check_payment_loop(self, record: dict, already_claimed: bool = False) -> None:
        """Checks for four hours: 10×1 min, then 5 min to one hour, then 15 min."""
        payment_id = record["payment_id"]
        if payment_id in self._active_checks and not already_claimed:
            return

        if not already_claimed:
            self._active_checks.add(payment_id)
        payment_repo = PaymentRepo(self.pool)
        created_at = self._as_aware(record["created_at"])
        deadline = created_at + self.PAYMENT_WINDOW
        logger.info(f"🔄 Start checking payment {payment_id} for user {record['user_id']}")

        try:
            while datetime.now(timezone.utc) < deadline:
                elapsed = datetime.now(timezone.utc) - created_at
                remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
                await asyncio.sleep(min(self._next_interval(elapsed), max(0, remaining)))

                try:
                    remote_payment = await asyncio.to_thread(Payment.find_one, payment_id)
                    if remote_payment.status == "succeeded":
                        if not self._matches_record(remote_payment, record):
                            logger.error(f"Payment {payment_id} does not match its local order; not fulfilling it.")
                            return
                        fulfilled = await self._fulfill_purchase(payment_id)
                        if fulfilled:
                            await self._notify_fulfillment(fulfilled)
                        return

                    if remote_payment.status == "canceled":
                        await payment_repo.update_yookassa_status(payment_id, "canceled")
                        logger.info(f"❌ Payment {payment_id} canceled")
                        return
                except Exception as exc:
                    logger.error(f"Error checking payment {payment_id}: {exc}")

            await payment_repo.expire_payment(payment_id)
            logger.info(f"⏳ Stop checking payment {payment_id} (4-hour timeout)")
        finally:
            self._active_checks.discard(payment_id)

    @staticmethod
    def _matches_record(remote_payment, record: dict) -> bool:
        try:
            remote_amount = int(float(remote_payment.amount.value))
            metadata_user_id = str(remote_payment.metadata.get("user_id"))
            return (
                remote_payment.amount.currency == "RUB"
                and remote_amount == int(record["amount"])
                and metadata_user_id == str(record["user_id"])
            )
        except (AttributeError, TypeError, ValueError):
            return False

    async def _fulfill_purchase(self, payment_id: str) -> Optional[dict]:
        """Atomically changes user balances and marks exactly this payment fulfilled."""
        purchase_bonus_setting = await SettingsRepo(self.pool).get_setting("karma_subscription_purchase_bonus")
        try:
            purchase_bonus = int(purchase_bonus_setting["value"]) if purchase_bonus_setting else 100
        except (TypeError, ValueError):
            purchase_bonus = 100
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                record = await conn.fetchrow(
                    "SELECT * FROM payments_yookassa WHERE payment_id = $1 FOR UPDATE;",
                    payment_id,
                )
                if not record or record["status"] == "fulfilled":
                    return None
                if record["status"] != "pending":
                    logger.warning(f"Payment {payment_id} has unexpected status {record['status']}.")
                    return None

                user = await conn.fetchrow(
                    "SELECT * FROM users WHERE user_id = $1 FOR UPDATE;", record["user_id"]
                )
                if not user:
                    logger.error(f"User {record['user_id']} is missing for payment {payment_id}.")
                    return None

                payload = record["payload"]
                result = {
                    "user_id": record["user_id"],
                    "amount": record["amount"],
                }
                if payload.startswith("buy_karma_"):
                    karma_add = int(payload.rsplit("_", 1)[1])
                    new_karma = await conn.fetchval(
                        "UPDATE users SET karma = karma + $2 WHERE user_id = $1 RETURNING karma;",
                        record["user_id"],
                        karma_add,
                    )
                    await conn.execute(
                        "INSERT INTO payments_internal (user_id, type_operation, amount) VALUES ($1, $2, $3);",
                        record["user_id"],
                        "yookassa_karma_purchase",
                        karma_add,
                    )
                    result.update(kind="karma", karma=karma_add, new_karma=int(new_karma))
                elif payload.startswith("buy_sub_"):
                    days = int(payload.rsplit("_", 1)[1])
                    now = datetime.now()
                    current_premium = user["premium_date"]
                    premium_date = (
                        current_premium + timedelta(days=days)
                        if current_premium and current_premium > now
                        else now + timedelta(days=days)
                    )
                    bonus = purchase_bonus
                    new_karma = await conn.fetchval(
                        """
                        UPDATE users SET premium_date = $2, karma = karma + $3
                        WHERE user_id = $1 RETURNING karma;
                        """,
                        record["user_id"],
                        premium_date,
                        bonus,
                    )
                    await conn.execute(
                        "INSERT INTO payments_internal (user_id, type_operation, amount) VALUES ($1, $2, $3);",
                        record["user_id"],
                        "yookassa_premium_bonus",
                        bonus,
                    )
                    result.update(
                        kind="subscription",
                        days=days,
                        premium_date=premium_date,
                        bonus=bonus,
                        new_karma=int(new_karma),
                    )
                else:
                    logger.error(f"Unknown payment payload for {payment_id}: {payload}")
                    return None

                await conn.execute(
                    "UPDATE payments_yookassa SET status = 'fulfilled' WHERE payment_id = $1;",
                    payment_id,
                )
                return result

    async def _notify_fulfillment(self, result: dict) -> None:
        user_id = result["user_id"]
        if result["kind"] == "karma":
            await send_text(
                self.bot,
                user_id,
                "✅ <b>Оплата прошла успешно!</b>\n\n"
                f"Вам начислено: <b>{result['karma']}</b> ✨\n"
                f"Ваш баланс: <b>{result['new_karma']}</b> ✨",
            )
            await self._log_to_admin(user_id, f"{result['karma']} Кармы", result["amount"])
            return

        date_text = result["premium_date"].strftime("%d.%m.%Y")
        await send_text(
            self.bot,
            user_id,
            "✅ <b>Премиум-подписка активирована!</b>\n\n"
            f"Действует до: <b>{date_text}</b>\n"
            f"Бонус за покупку: +{result['bonus']} ✨",
            message_effect_id="5104841245755180586",
        )
        await self._log_to_admin(user_id, f"Подписка {result['days']} дн.", result["amount"])

    async def _log_to_admin(self, user_id: int, item_name: str, amount: int) -> None:
        try:
            await self.bot.send_message(
                LOG_GROUP_ID,
                "💰 <b>Успешная оплата (ЮKassa)</b>\n\n"
                f"👤 User: <code>{user_id}</code>\n"
                f"🛍 Товар: {item_name}\n"
                f"💵 Сумма: {amount} ₽",
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Failed to write YooKassa payment to the admin log")
