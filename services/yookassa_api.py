# services/yookassa_api.py
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Tuple

from yookassa import Configuration, Payment
from loguru import logger
from aiogram import Bot

# Импорты проекта
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, LOG_GROUP_ID
from db import UserRepo, PaymentRepo
from utils.sender import send_text

# Настройка ЮКассы
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY


class YooKassaService:
    def __init__(self, bot: Bot, pool):
        self.bot = bot
        self.pool = pool

    async def create_payment(self, amount: int, description: str, user_id: int) -> Tuple[str, str]:
        """
        Создает платеж в ЮКассе.
        Возвращает (confirmation_url, payment_id).
        """
        idempotence_key = str(uuid.uuid4())

        # Создание платежа через синхронную библиотеку (yookassa),
        # поэтому оборачиваем в to_thread для асинхронности, если нагрузка большая,
        # но для редких платежей можно и так.
        payment = Payment.create({
            "amount": {
                "value": f"{amount}.00",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/rus_tarot_bot"  # Ссылка на твоего бота
            },
            "capture": True,
            "description": description,
            "metadata": {"user_id": user_id}
        }, idempotence_key)

        return payment.confirmation.confirmation_url, payment.id

    async def check_payment_loop(self, payment_id: str, user_id: int, payload: str, amount: int):
        """
        Фоновая задача: проверяет статус платежа каждые 15 секунд в течение 15 минут.
        """
        logger.info(f"🔄 Start checking payment {payment_id} for user {user_id}")

        payment_repo = PaymentRepo(self.pool)
        user_repo = UserRepo(self.pool)

        # 60 попыток * 15 секунд = 15 минут ожидания
        for _ in range(60):
            await asyncio.sleep(15)

            try:
                # Получаем актуальный статус из ЮКассы
                payment = Payment.find_one(payment_id)

                if payment.status == "succeeded":
                    # Проверяем, не обработан ли он уже в нашей БД (чтобы не начислить дважды)
                    record = await payment_repo.get_yookassa_payment(payment_id)
                    if record and record['status'] == 'succeeded':
                        return

                    # 1. Обновляем статус в БД
                    await payment_repo.update_yookassa_status(payment_id, "succeeded")

                    # 2. Выдаем товар
                    await self._fulfill_purchase(user_id, payload, amount, user_repo)
                    return

                elif payment.status == "canceled":
                    await payment_repo.update_yookassa_status(payment_id, "canceled")
                    logger.info(f"❌ Payment {payment_id} canceled")
                    return

            except Exception as e:
                logger.error(f"Error checking payment {payment_id}: {e}")

        logger.info(f"⏳ Stop checking payment {payment_id} (timeout)")

    async def _fulfill_purchase(self, user_id: int, payload: str, amount: int, user_repo: UserRepo):
        """
        Начисление бонусов после успешной оплаты.
        """
        user = await user_repo.get_user(user_id)
        if not user:
            return

        user_data = dict(user)

        # --- Обработка Кармы ---
        if payload.startswith("buy_karma_"):
            # payload вида buy_karma_100
            try:
                karma_add = int(payload.split("_")[2])
            except (IndexError, ValueError):
                karma_add = 0

            new_karma = user_data["karma"] + karma_add

            await user_repo.update_user(user_id, karma=new_karma)

            # Уведомление пользователю
            await send_text(
                self.bot, user_id,
                f"✅ <b>Оплата прошла успешно!</b>\n\n"
                f"Вам начислено: <b>{karma_add}</b> ✨\n"
                f"Ваш баланс: <b>{new_karma}</b> ✨"
            )

            # Лог в канал
            await self._log_to_admin(user_id, f"{karma_add} Кармы", amount)

        # --- Обработка Подписки ---
        elif payload.startswith("buy_sub_"):
            # payload вида buy_sub_30
            try:
                days = int(payload.split("_")[2])
            except (IndexError, ValueError):
                days = 30

            now = datetime.now()
            current_prem = user_data.get("premium_date")

            if current_prem and current_prem > now:
                new_date = current_prem + timedelta(days=days)
            else:
                new_date = now + timedelta(days=days)

            # Бонус за покупку подписки
            bonus = 100
            new_karma = user_data["karma"] + bonus

            await user_repo.update_user(user_id, premium_date=new_date, karma=new_karma)

            fmt_date = new_date.strftime("%d.%m.%Y")

            await send_text(
                self.bot, user_id,
                f"✅ <b>Премиум-подписка активирована!</b>\n\n"
                f"Действует до: <b>{fmt_date}</b>\n"
                f"Бонус за покупку: +{bonus} ✨",
                message_effect_id="5104841245755180586"  # Эффект салюта (если есть)
            )

            # Лог в канал
            await self._log_to_admin(user_id, f"Подписка {days} дн.", amount)

    async def _log_to_admin(self, user_id: int, item_name: str, amount: int):
        """Отправка лога в админский чат."""
        try:
            await self.bot.send_message(
                LOG_GROUP_ID,
                f"💰 <b>Успешная оплата (ЮKassa)</b>\n\n"
                f"👤 User: <code>{user_id}</code>\n"
                f"🛍 Товар: {item_name}\n"
                f"💵 Сумма: {amount} ₽",
                parse_mode="HTML"
            )
        except Exception:
            pass