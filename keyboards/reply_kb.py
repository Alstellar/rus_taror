# keyboards/reply_kb.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Генерирует главное меню бота."""
    buttons = [
        [KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="🌙 Гороскоп"), KeyboardButton(text="🃏 Таро расклады")],
        [KeyboardButton(text="💤 Сонник"), KeyboardButton(text="🏪 Маркетплейс")],
        [KeyboardButton(text="📌 Наши проекты"), KeyboardButton(text="ℹ️ Инфо")],
        [KeyboardButton(text="📜 Пользовательское соглашение")]
    ]

    if is_admin:
        buttons.append([KeyboardButton(text="⚙️ Админ-панель")])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите пункт меню..."
    )

def get_cancel_reply_keyboard() -> ReplyKeyboardMarkup:
    """
    Клавиатура, которая показывается, когда бот ждет ввод текста.
    """
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        is_persistent=True
    )