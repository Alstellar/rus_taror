# handlers/marketplace.py
import asyncpg
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from db import SettingsRepo, PaymentRepo
from services.yookassa_api import YooKassaService
from utils.sender import send_text, edit_text
from keyboards.inline_kb import get_marketplace_keyboard, get_payment_link_keyboard

marketplace_router = Router()


# --- Главное меню Маркетплейса ---
@marketplace_router.message(F.text == "🏪 Маркетплейс")
@marketplace_router.message(Command("shop"))
async def show_marketplace(message: Message, db_pool: asyncpg.Pool, bot: Bot):
    settings_repo = SettingsRepo(db_pool)
    prices = await settings_repo.get_all_settings()

    text = (
        "🏪 <b>Маркетплейс</b>\n\n"
        "Здесь вы можете приобрести карму или оформить Премиум-подписку.\n\n"
        "👑 <b>Преимущества Премиума:</b>\n"
        "• Доступ к смене Персонажей 🎭\n"
        "• Доступ к смене Колод 🃏\n"
        "• Ежедневное начисление кармы ✨"
    )

    await send_text(bot, message.chat.id, text, reply_markup=get_marketplace_keyboard(prices))


# --- Возврат в меню / Переход из профиля (Callback) ---
@marketplace_router.callback_query(F.data.in_({"marketplace_menu", "marketplace_buy_karma"}))
async def back_to_marketplace(callback: CallbackQuery, db_pool: asyncpg.Pool, bot: Bot):
    settings_repo = SettingsRepo(db_pool)
    prices = await settings_repo.get_all_settings()

    text = (
        "🏪 <b>Маркетплейс</b>\n\n"
        "Здесь вы можете приобрести карму или оформить Премиум-подписку.\n\n"
        "👑 <b>Преимущества Премиума:</b>\n"
        "• Доступ к смене Персонажей 🎭\n"
        "• Доступ к смене Колод 🃏\n"
        "• Ежедневное начисление кармы ✨"
    )

    await edit_text(
        bot,
        callback.message.chat.id,
        callback.message.message_id,
        text,
        reply_markup=get_marketplace_keyboard(prices)
    )
    await callback.answer()


# --- Обработка покупки ---
@marketplace_router.callback_query(F.data.startswith("buy_"))
async def process_buy_click(callback: CallbackQuery, db_pool: asyncpg.Pool, bot: Bot):
    item_type = callback.data  # buy_sub_30, buy_karma_100
    user_id = callback.from_user.id

    # 1. Получаем цены
    settings_repo = SettingsRepo(db_pool)
    payment_repo = PaymentRepo(db_pool)
    prices = await settings_repo.get_all_settings()

    amount = 0
    description = ""

    # Маппинг товаров
    if item_type == "buy_sub_30":
        amount = int(prices["price_subscription"]["value"])
        description = "Премиум подписка (30 дней)"
    elif item_type == "buy_karma_100":
        amount = int(prices["price_karma_100"]["value"])
        description = "100 Кармы"
    elif item_type == "buy_karma_500":
        amount = int(prices["price_karma_500"]["value"])
        description = "500 Кармы"
    elif item_type == "buy_karma_1000":
        amount = int(prices["price_karma_1000"]["value"])
        description = "1000 Кармы"
    else:
        await callback.answer("Ошибка товара")
        return

    await callback.answer("⏳ Создаю счет на оплату...")

    # 2. Инициализируем сервис ЮКассы
    yookassa = YooKassaService(bot, db_pool)

    try:
        # Создаем платеж в ЮКассе
        payment_url, payment_id = await yookassa.create_payment(amount, description, user_id)

        # 3. Сохраняем "черновик" платежа в БД
        await payment_repo.add_yookassa_payment(
            user_id=user_id,
            amount=amount,
            payload=item_type,
            payment_id=payment_id
        )

        # 4. Запускаем фоновую задачу проверки
        # create_task "отпускает" управление, код идет дальше, а проверка крутится параллельно
        asyncio.create_task(
            yookassa.check_payment_loop(payment_id, user_id, item_type, amount)
        )

        # 5. Показываем кнопку оплаты пользователю
        await edit_text(
            bot,
            callback.message.chat.id,
            callback.message.message_id,
            f"💳 <b>Счет на оплату: {amount}₽</b>\n"
            f"Товар: {description}\n\n"
            f"<i>Нажмите кнопку ниже для оплаты. После успешной транзакции бот автоматически начислит вам покупку (обычно в течение 1 минуты).</i>",
            reply_markup=get_payment_link_keyboard(payment_url)
        )

    except Exception as e:
        await send_text(bot, callback.message.chat.id, f"❌ Ошибка создания платежа: {e}")