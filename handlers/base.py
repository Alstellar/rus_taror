# handlers/base.py
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from utils.sender import send_text, delete_message, edit_text
from keyboards.reply_kb import get_main_menu_keyboard
from keyboards.inline_kb import get_offer_keyboard
from config import BOT_ADMIN_IDS, PUBLIC_OFFER_URL

base_router = Router()


# --- Кнопка "Домой" (Инлайн) ---
@base_router.callback_query(F.data == "nav_home")
async def nav_home_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    # Удаляем старое инлайн сообщение, чтобы не засорять чат
    await delete_message(bot, callback.message.chat.id, callback.message.message_id)

    is_admin = callback.from_user.id in BOT_ADMIN_IDS
    await send_text(
        bot,
        callback.message.chat.id,
        "🏠 Вы в главном меню.",
        reply_markup=get_main_menu_keyboard(is_admin)
    )
    await callback.answer()


# --- Обработчики нижнего меню ---

@base_router.message(F.text == "📌 Наши проекты")
async def projects_handler(message: Message, bot: Bot):
    text = (
        "<b>📌 Наши проекты</b>\n\n"
        "Я разрабатываю не только этого бота!\n\n"
        "1. <b>@memtaro_bot</b> — мемные предсказания на каждый день.\n"
        "2. <b>@remindflow_bot</b> - удобная напоминалка\n"
        "3. <b>@my_freelancer_notes</b> — канал разработчика о буднях и коде.\n\n"
        "<i>Подпишитесь на канал разработчика и получайте ежедневный бонус +1 к карме!</i>"
    )
    await send_text(bot, message.chat.id, text)


@base_router.message(F.text == "ℹ️ Инфо")
@base_router.message(Command("info"))
async def info_handler(message: Message, bot: Bot):
    text = (
        "<b>ℹ️ Информация о боте</b>\n\n"
        "Я — ИИ-Таролог, использующий мощнейшие нейросети для генерации раскладов.\n\n"
        "Моя цель — дать вам совет и пищу для размышлений.\n\n"
        "<b>📂 Навигация:</b>\n"
        "/start — Главное меню\n"
        "/profile — Профиль и настройки\n"
        "/horoscope — Гороскоп на сегодня\n"
        "/tarot — Расклады Таро\n"
        "/dream — Сонник\n"
        "/shop — Покупка кармы и премиума\n\n"
        "<b>📜 Оферта и оплата:</b>\n"
        f"{PUBLIC_OFFER_URL}\n"
        "Покупки, сроки оказания услуг и возвраты регулируются публичной офертой.\n\n"
        "<b>📞 Поддержка:</b>\n"
        "Если у вас возникли проблемы с оплатой, начислением кармы, подпиской или работой бота, напишите:\n\n"
        "Telegram: @Alstellar\n"
        "Email: lekha-legkv@yandex.ru\n\n"
    )
    await send_text(bot, message.chat.id, text)


@base_router.message(Command("support"))
async def support_handler(message: Message, bot: Bot):
    text = (
        "<b>📞 Техническая поддержка</b>\n\n"
        "Если у вас возникли проблемы с оплатой, начислением кармы, подпиской или работой бота, напишите нам:\n\n"
        "Telegram: @Alstellar\n"
        "Email: lekha-legkv@yandex.ru"
    )
    await send_text(bot, message.chat.id, text)


@base_router.message(F.text.in_({"📜 Оферта и условия", "📜 Пользовательское соглашение"}))
async def agreement_handler(message: Message, bot: Bot):
    text = (
        "<b>📜 Оферта и условия использования</b>\n\n"
        "Полные правила оформления заказа, способы оплаты, сроки оказания услуг, условия возврата и реквизиты исполнителя опубликованы в публичной оферте.\n\n"
        "Расклады, гороскопы и толкования снов носят информационно-развлекательный характер и не являются профессиональной консультацией.\n\n"
        "Продолжая использование бота, вы подтверждаете, что ознакомились с публичной офертой и принимаете ее условия.\n\n"
        "Поддержка: @Alstellar\n"
        "Email: lekha-legkv@yandex.ru"
    )
    await send_text(bot, message.chat.id, text, reply_markup=get_offer_keyboard())
