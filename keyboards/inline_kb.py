# keyboards/inline_kb.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.card_mapping import TAROT_DECK_MAPPING
from utils.personas import PERSONAS
from db import SettingsRepo  # Для цен, если используется внутри функций


# --- Общие кнопки ---
def btn_home() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="🏠 В главное меню", callback_data="nav_home")


def btn_back_profile() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")


# --- Профиль ---
def get_profile_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # Добавляем основные кнопки
    kb.button(text="📅 Изменить дату рождения", callback_data="profile_set_dob")
    kb.button(text="🃏 Сменить колоду", callback_data="profile_change_deck")
    kb.button(text="🎭 Сменить персонажа", callback_data="profile_change_persona")
    kb.button(text="💳 Пополнить карму", callback_data="marketplace_buy_karma")

    # Выстраиваем эти кнопки в 1 столбец
    kb.adjust(1)

    # Потом добавляем кнопку "Домой" отдельным рядом
    kb.row(btn_home())
    return kb.as_markup()


# --- Таро и колоды ---
def get_decks_keyboard(current_deck: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for deck_key, deck_name in TAROT_DECK_MAPPING.items():
        text = f"✅ {deck_name}" if deck_key == current_deck else deck_name
        kb.button(text=text, callback_data=f"set_deck_{deck_key}")

    # Выстраиваем список колод по 1 в ряд
    kb.adjust(1)

    # Кнопки навигации добавляем отдельными рядами
    kb.row(btn_back_profile())
    kb.row(btn_home())
    return kb.as_markup()


def get_personas_keyboard(current_persona: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, data in PERSONAS.items():
        text = f"✅ {data['name']}" if key == current_persona else data['name']
        kb.button(text=text, callback_data=f"set_persona_{key}")

    # Выстраиваем список персонажей по 1 в ряд
    kb.adjust(1)

    # Навигация
    kb.row(btn_back_profile())
    kb.row(btn_home())
    return kb.as_markup()


def get_tarot_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🃏 Карта дня (Бесплатно)", callback_data="tarot_daily")
    kb.button(text="🔍 Одиночная карта", callback_data="tarot_one_card")
    kb.button(text="🔮 Три карты (П-Н-Б)", callback_data="tarot_ppf")
    kb.button(text="✝️ Кельтский крест", callback_data="tarot_celtic")
    kb.button(text="🤝 Знакомство с колодой", callback_data="tarot_intro")

    # Выстраиваем расклады по 1 в ряд
    kb.adjust(1)

    kb.row(btn_home())
    return kb.as_markup()


# --- Таро ---
def get_tarot_request_keyboard() -> InlineKeyboardMarkup:
    """Кнопка для начала ввода вопроса к картам."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔮 Ввести запрос", callback_data="tarot_enter_query")
    kb.adjust(1)
    kb.row(btn_home())
    return kb.as_markup()



# --- Сонник ---
def get_dream_start_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💤 Рассказать сон", callback_data="dream_tell")
    # Тут adjust не обязателен, так как кнопка всего одна, но для порядка оставим
    kb.adjust(1)
    kb.row(btn_home())
    return kb.as_markup()


# --- Маркетплейс ---
def get_marketplace_keyboard(prices: dict) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    # Подписка
    sub_price = prices.get("price_subscription", {}).get("value", "199")
    kb.button(text=f"👑 Премиум подписка ({sub_price}₽)", callback_data="buy_sub_30")

    # Карма
    k100 = prices.get("price_karma_100", {}).get("value", "10")
    k500 = prices.get("price_karma_500", {}).get("value", "40")
    k1000 = prices.get("price_karma_1000", {}).get("value", "70")

    kb.button(text=f"✨ 100 Кармы ({k100}₽)", callback_data="buy_karma_100")
    kb.button(text=f"✨ 500 Кармы ({k500}₽)", callback_data="buy_karma_500")
    kb.button(text=f"✨ 1000 Кармы ({k1000}₽)", callback_data="buy_karma_1000")

    # Делаем все кнопки в 1 столбец (так красивее для цен)
    kb.adjust(1)

    kb.row(btn_home())
    return kb.as_markup()


def get_payment_link_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к оплате", url=url)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="marketplace_menu")]
    ])


# --- Админская рассылка ---
def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✉️ Рассылка одному", callback_data="admin_mail_one")
    kb.button(text="📢 Рассылка всем", callback_data="admin_mail_all")

    kb.adjust(1)  # Вертикально
    kb.row(btn_home())
    return kb.as_markup()


def get_confirm_broadcast_keyboard() -> InlineKeyboardMarkup:
    # Тут можно оставить в одну строку (2 кнопки), либо сделать вертикально
    # Сделаем вертикально для единообразия
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить и отправить", callback_data="confirm_broadcast")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_broadcast")]
    ])


# --- Общая кнопка отмены ---
def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])