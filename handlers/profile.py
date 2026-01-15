# handlers/profile.py
import asyncpg
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command

from db import UserRepo
from utils.sender import send_text, edit_text, delete_message
# Импортируем is_premium из helpers
from utils.helpers import get_zodiac_sign, is_premium
from utils.card_mapping import TAROT_DECK_MAPPING
from utils.personas import PERSONAS
from keyboards.inline_kb import get_profile_keyboard, get_decks_keyboard, get_cancel_keyboard, get_personas_keyboard


class ProfileStates(StatesGroup):
    waiting_for_dob = State()


profile_router = Router()


# --- 1. Просмотр профиля ---
@profile_router.message(F.text == "👤 Профиль")
@profile_router.message(Command("profile"))
async def show_profile(message: Message, db_pool: asyncpg.Pool, bot: Bot):
    repo = UserRepo(db_pool)
    user_record = await repo.get_user(message.from_user.id)

    if not user_record:
        await send_text(bot, message.chat.id, "⚠️ Профиль не найден. Нажмите /start")
        return

    user = dict(user_record)

    dob = user.get("added_date_of_birth")
    if dob:
        dob_str = dob.strftime("%d.%m.%Y")
        zodiac = get_zodiac_sign(dob)
    else:
        dob_str = "Не указана"
        zodiac = "—"

    deck_key = user.get("choice_tarot")
    deck_name = TAROT_DECK_MAPPING.get(deck_key, "Неизвестная колода")

    persona_key = user.get("narrative_persona", "default")
    persona_data = PERSONAS.get(persona_key, PERSONAS["default"])
    persona_name = persona_data["name"]

    # Проверка статуса для отображения текста
    has_premium = is_premium(user)
    prem_str = "АКТИВЕН ✅" if has_premium else "Не активен ❌"
    if has_premium:
        prem_date = user['premium_date'].strftime("%d.%m.%Y")
        prem_str += f" (до {prem_date})"

    text = (
        f"👤 <b>Ваш Профиль</b>\n\n"
        f"🆔 ID: <code>{user['user_id']}</code>\n"
        f"📅 Дата рождения: <b>{dob_str}</b>\n"
        f"💫 Знак Зодиака: <b>{zodiac}</b>\n\n"
        f"🃏 Активная колода: <b>{deck_name}</b>\n"
        f"🎭 Стиль общения: <b>{persona_name}</b>\n"
        f"✨ Карма: <b>{user['karma']}</b>\n"
        f"💎 Премиум: <b>{prem_str}</b>"
    )

    # Клавиатура теперь одинаковая для всех
    await send_text(bot, message.chat.id, text, reply_markup=get_profile_keyboard())


# --- 2. Возврат в профиль ---
@profile_router.callback_query(F.data == "back_to_profile")
async def back_to_profile_handler(callback: CallbackQuery, db_pool: asyncpg.Pool, bot: Bot):
    repo = UserRepo(db_pool)
    user_record = await repo.get_user(callback.from_user.id)
    user = dict(user_record)

    dob = user.get("added_date_of_birth")
    dob_str = dob.strftime("%d.%m.%Y") if dob else "Не указана"
    zodiac = get_zodiac_sign(dob) if dob else "—"
    deck_name = TAROT_DECK_MAPPING.get(user.get("choice_tarot"), "Неизвестная")

    persona_key = user.get("narrative_persona", "default")
    persona_name = PERSONAS.get(persona_key, PERSONAS["default"])["name"]

    has_premium = is_premium(user)
    prem_str = "АКТИВЕН ✅" if has_premium else "Не активен ❌"
    if has_premium:
        prem_date = user['premium_date'].strftime("%d.%m.%Y")
        prem_str += f" (до {prem_date})"

    text = (
        f"👤 <b>Ваш Профиль</b>\n\n"
        f"🆔 ID: <code>{user['user_id']}</code>\n"
        f"📅 Дата рождения: <b>{dob_str}</b>\n"
        f"💫 Знак Зодиака: <b>{zodiac}</b>\n\n"
        f"🃏 Активная колода: <b>{deck_name}</b>\n"
        f"🎭 Стиль общения: <b>{persona_name}</b>\n"
        f"✨ Карма: <b>{user['karma']}</b>\n"
        f"💎 Премиум: <b>{prem_str}</b>"
    )

    await edit_text(
        bot,
        callback.message.chat.id,
        callback.message.message_id,
        text,
        reply_markup=get_profile_keyboard()
    )
    await callback.answer()


# --- 3. Смена Персонажа (ПРОВЕРКА PREMIUM) ---
@profile_router.callback_query(F.data == "profile_change_persona")
async def show_personas_handler(callback: CallbackQuery, db_pool: asyncpg.Pool, bot: Bot):
    repo = UserRepo(db_pool)
    user = await repo.get_user(callback.from_user.id)

    # 🛑 Блокируем доступ, если нет премиума
    if not is_premium(dict(user)):
        await callback.answer("👑 Эта функция доступна только в Премиум-подписке!\nЗагляните в Маркетплейс.",
                              show_alert=True)
        return

    current_persona = user.get("narrative_persona", "default")

    await edit_text(
        bot,
        callback.message.chat.id,
        callback.message.message_id,
        "🎭 <b>Выберите стиль общения (Персонажа):</b>\n\n"
        "Персонаж будет проводить для вас расклады и давать советы в своем уникальном стиле.",
        reply_markup=get_personas_keyboard(current_persona)
    )
    await callback.answer()


@profile_router.callback_query(F.data.startswith("set_persona_"))
async def set_persona_handler(callback: CallbackQuery, db_pool: asyncpg.Pool, bot: Bot):
    repo = UserRepo(db_pool)
    user = await repo.get_user(callback.from_user.id)

    # Повторная проверка на случай истечения
    if not is_premium(dict(user)):
        await callback.answer("👑 Подписка истекла!", show_alert=True)
        await back_to_profile_handler(callback, db_pool, bot)
        return

    new_persona_key = callback.data.replace("set_persona_", "")

    if new_persona_key not in PERSONAS:
        await callback.answer("Ошибка выбора", show_alert=True)
        return

    await repo.update_user(callback.from_user.id, narrative_persona=new_persona_key)

    persona_name = PERSONAS[new_persona_key]["name"]
    await callback.answer(f"Выбран персонаж: {persona_name}")

    await edit_text(
        bot,
        callback.message.chat.id,
        callback.message.message_id,
        "🎭 <b>Выберите стиль общения (Персонажа):</b>\n\n"
        "Персонаж будет проводить для вас расклады и давать советы в своем уникальном стиле.",
        reply_markup=get_personas_keyboard(new_persona_key)
    )


# --- 4. Смена Колоды (ПРОВЕРКА PREMIUM) ---
@profile_router.callback_query(F.data == "profile_change_deck")
async def show_decks_handler(callback: CallbackQuery, db_pool: asyncpg.Pool, bot: Bot):
    repo = UserRepo(db_pool)
    user = await repo.get_user(callback.from_user.id)

    # 🛑 Блокируем доступ, если нет премиума
    if not is_premium(dict(user)):
        await callback.answer("👑 Смена колоды доступна только в Премиум-подписке!\nЗагляните в Маркетплейс.",
                              show_alert=True)
        return

    current_deck = user.get("choice_tarot")
    await edit_text(
        bot,
        callback.message.chat.id,
        callback.message.message_id,
        "🃏 <b>Выберите колоду Таро:</b>",
        reply_markup=get_decks_keyboard(current_deck)
    )
    await callback.answer()


@profile_router.callback_query(F.data.startswith("set_deck_"))
async def set_deck_handler(callback: CallbackQuery, db_pool: asyncpg.Pool, bot: Bot):
    repo = UserRepo(db_pool)
    user = await repo.get_user(callback.from_user.id)

    # Повторная проверка
    if not is_premium(dict(user)):
        await callback.answer("👑 Подписка истекла!", show_alert=True)
        await back_to_profile_handler(callback, db_pool, bot)
        return

    new_deck_key = callback.data.replace("set_deck_", "")
    if new_deck_key not in TAROT_DECK_MAPPING:
        return

    await repo.update_user(callback.from_user.id, choice_tarot=new_deck_key)
    await callback.answer(f"Выбрана колода: {TAROT_DECK_MAPPING[new_deck_key]}")
    await edit_text(
        bot,
        callback.message.chat.id,
        callback.message.message_id,
        "🃏 <b>Выберите колоду Таро:</b>",
        reply_markup=get_decks_keyboard(new_deck_key)
    )


# --- 5. Изменение Даты Рождения (БЕЗ ПРОВЕРКИ, ДОСТУПНО ВСЕМ) ---
@profile_router.callback_query(F.data == "profile_set_dob")
async def start_set_dob(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await send_text(
        bot,
        callback.message.chat.id,
        "Введите вашу дату рождения в формате <b>ДД.ММ.ГГГГ</b>\n"
        "<i>Например: 25.03.1995</i>",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ProfileStates.waiting_for_dob)
    await callback.answer()


@profile_router.message(ProfileStates.waiting_for_dob)
async def process_dob_input(message: Message, state: FSMContext, db_pool: asyncpg.Pool, bot: Bot):
    text_input = message.text.strip()
    try:
        dob_date = datetime.strptime(text_input, "%d.%m.%Y").date()
        if dob_date.year < 1920 or dob_date.year > datetime.now().year:
            await send_text(bot, message.chat.id, "❌ Похоже на ошибку в годе. Попробуйте еще раз.")
            return

        repo = UserRepo(db_pool)
        await repo.update_user(message.from_user.id, added_date_of_birth=dob_date)

        await send_text(bot, message.chat.id, f"✅ Дата рождения сохранена: <b>{text_input}</b>")
        await state.clear()
        await show_profile(message, db_pool, bot)

    except ValueError:
        await send_text(bot, message.chat.id, "❌ Неверный формат. Используйте ДД.ММ.ГГГГ",
                        reply_markup=get_cancel_keyboard())


# --- 6. Отмена ---
@profile_router.callback_query(F.data == "cancel_action")
async def cancel_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    await delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await callback.answer("Действие отменено")