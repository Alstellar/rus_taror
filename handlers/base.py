# handlers/base.py
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from utils.sender import send_text, delete_message, edit_text
from keyboards.reply_kb import get_main_menu_keyboard
from config import BOT_ADMIN_IDS

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
        "<b>📞 Поддержка:</b>\n"
        "/support — Связаться с разработчиком\n\n"
    )
    await send_text(bot, message.chat.id, text)


@base_router.message(Command("support"))
async def support_handler(message: Message, bot: Bot):
    text = (
        "<b>📞 Техническая поддержка</b>\n\n"
        "Если у вас возникли проблемы с оплатой, бот не отвечает или есть предложения:\n\n"
        "📩 Пишите сюда: @Alstellar"
    )
    await send_text(bot, message.chat.id, text)


@base_router.message(F.text == "📜 Пользовательское соглашение")
async def agreement_handler(message: Message, bot: Bot):
    text = (
        "<b>📜 Пользовательское соглашение</b>\n\n"
        "1. <b>Развлекательный характер:</b> Все предсказания генерируются искусственным интеллектом и носят исключительно развлекательный характер.\n\n"
        "2. <b>Ответственность:</b> Администрация не несет ответственности за принятые вами решения на основе ответов бота.\n\n"
        "3. <b>Возвраты:</b> Покупки цифровых товаров (карма, подписка) являются окончательными и возврату не подлежат, кроме случаев технического сбоя.\n\n"
        "4. <b>Правила:</b> Запрещено использовать бота для спама или мошенничества.\n\n"
        "<i>Используя бота, вы принимаете эти условия.</i>"
    )
    await send_text(bot, message.chat.id, text)