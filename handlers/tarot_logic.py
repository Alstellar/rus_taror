import asyncpg
import asyncio
from datetime import date
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command

# Импорты проекта
from db import UserRepo, PredictRepo, SettingsRepo, HoroscopeRepo, PaymentRepo, ImageRepo
from services.llm_generator import LLMService
from utils.helpers import get_zodiac_sign
from utils.personas import PERSONAS
from utils.prompts import get_system_prompt, make_horoscope_prompt, make_dream_prompt, make_tarot_prompt
from utils.sender import send_text, send_photo, send_media_group, delete_message, send_loading_animation
from utils.tarot_layouts import TAROT_LAYOUTS_INFO

# Клавиатуры
from keyboards.inline_kb import get_tarot_menu_keyboard, get_tarot_request_keyboard, get_dream_start_keyboard, btn_back_to_main_menu, get_tarot_intro_keyboard
from keyboards.reply_kb import get_cancel_reply_keyboard, get_main_menu_keyboard
from config import BOT_ADMIN_IDS

tarot_router = Router()
llm_service = LLMService()


class TarotStates(StatesGroup):
    waiting_for_dream = State()
    waiting_for_question = State()


# --- Вспомогательная функция проверки баланса ---
async def check_balance_and_get_price(
        user_id: int, setting_key: str, db_pool: asyncpg.Pool, bot: Bot, chat_id: int
) -> int:
    settings_repo = SettingsRepo(db_pool)
    user_repo = UserRepo(db_pool)

    setting = await settings_repo.get_setting(setting_key)
    price = int(setting["value"]) if setting else 0

    user = await user_repo.get_user(user_id)
    karma = user.get("karma", 0)

    if karma < price:
        await send_text(
            bot,
            chat_id,
            f"🚫 <b>Недостаточно кармы!</b>\n"
            f"Стоимость: {price} ✨\n"
            f"У вас: {karma} ✨\n\n"
            f"Пополните баланс в Маркетплейсе."
        )
        return -1
    return price


# ==========================
# ❌ ОБЩАЯ ОТМЕНА (REPLY)
# ==========================
@tarot_router.message(F.text == "❌ Отмена")
async def reply_cancel_handler(message: Message, state: FSMContext, bot: Bot):
    """Сбрасывает любое состояние и возвращает главное меню."""
    await state.clear()
    is_admin = message.from_user.id in BOT_ADMIN_IDS
    await send_text(
        bot,
        message.chat.id,
        "🏠 Действие отменено. Вы в главном меню.",
        reply_markup=get_main_menu_keyboard(is_admin)
    )


# ==========================
# 🔄 НАЗАД К МЕНЮ РАСКЛАДОВ
# ==========================
@tarot_router.callback_query(F.data == "back_to_tarot_menu")
async def back_to_tarot_menu_handler(callback: CallbackQuery, bot: Bot):
    await send_text(
        bot,
        callback.message.chat.id,
        "🃏 <b>Выберите тип расклада:</b>\n\n"
        "<i>Карта дня — бесплатно раз в сутки.\n"
        "Остальные расклады — за карму.</i>",
        reply_markup=get_tarot_menu_keyboard()
    )
    await callback.answer()


# ==========================
# 🌙 ГОРОСКОП
# ==========================
@tarot_router.message(F.text == "🌙 Гороскоп")
@tarot_router.message(Command("horoscope"))
async def horoscope_handler(message: Message, db_pool: asyncpg.Pool, bot: Bot):
    user_id = message.from_user.id
    user_repo = UserRepo(db_pool)
    horoscope_repo = HoroscopeRepo(db_pool)
    predict_repo = PredictRepo(db_pool)

    user = await user_repo.get_user(user_id)

    # 1. Проверка даты рождения
    dob = user.get("added_date_of_birth")
    if not dob:
        await send_text(bot, message.chat.id, "⚠️ Чтобы получить гороскоп, укажите дату рождения в <b>Профиле</b>.")
        return

    sign_emoji = get_zodiac_sign(dob)
    sign_name = sign_emoji.split()[0].lower()

    # 2. Проверяем кэш на сегодня
    today = date.today()
    cached = await horoscope_repo.get_horoscope(sign_name, today)

    if cached:
        # Если гороскоп есть в кэше
        # 1. Шлем гифку
        loading_msg = await send_loading_animation(bot, message.chat.id, "gifs_astro", db_pool)

        # 2. Имитируем бурную деятельность (пауза 3-5 сек)
        await asyncio.sleep(4)

        # 3. Удаляем гифку
        if loading_msg:
            await delete_message(bot, message.chat.id, loading_msg.message_id)

        # 4. Отправляем готовый текст
        await send_text(bot, message.chat.id, cached["content"])
        return

    # 3. Проверка баланса
    price = await check_balance_and_get_price(user_id, "price_daily_horoscope", db_pool, bot, message.chat.id)
    if price == -1: return

    loading_msg = await send_loading_animation(bot, message.chat.id, "gifs_astro", db_pool)

    # await send_text(bot, message.chat.id, "✨ Звезды шепчут... Составляю прогноз...")

    # 4. Генерация
    persona_key = user.get("narrative_persona", "default")
    sys_prompt = get_system_prompt(PERSONAS[persona_key]["prompt"])
    user_prompt = make_horoscope_prompt(sign_emoji, today.strftime("%d.%m.%Y"))

    response = await llm_service.generate_response(user_prompt, sys_prompt)

    # 3. УДАЛЯЕМ ГИФКУ
    if loading_msg:
        await delete_message(bot, message.chat.id, loading_msg.message_id)

    if not response:
        await send_text(bot, message.chat.id, "❌ Не удалось связаться с космосом. Попробуйте позже.")
        return

    # 5. Сохранение и списание
    await horoscope_repo.add_horoscope(sign_name, today, response)

    payment_repo = PaymentRepo(db_pool)
    await user_repo.update_user(user_id, karma=user['karma'] - price)
    await payment_repo.add_internal_transaction(user_id, "daily_horoscope", -price)
    await predict_repo.update_predicts(user_id, last_horoscope_daily_date=today)

    await send_text(bot, message.chat.id, response)


# ==========================
# 💤 СОННИК
# ==========================
@tarot_router.message(F.text == "💤 Сонник")
@tarot_router.message(Command("dream"))
async def dream_menu_handler(message: Message, bot: Bot):
    text = (
        "🌙 <b>Толкование снов</b>\n\n"
        "Сны — это язык нашего подсознания. Я помогу расшифровать образы, которые вы увидели.\n"
        "Нажмите кнопку ниже, чтобы начать сеанс."
    )
    await send_text(bot, message.chat.id, text, reply_markup=get_dream_start_keyboard())


@tarot_router.callback_query(F.data == "dream_tell")
async def dream_start_input(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await send_text(
        bot,
        callback.message.chat.id,
        "✍️ <b>Опишите ваш сон одним сообщением.</b>\n"
        "Постарайтесь вспомнить детали, цвета и эмоции.",
        reply_markup=get_cancel_reply_keyboard()
    )
    await state.set_state(TarotStates.waiting_for_dream)
    await callback.answer()


@tarot_router.message(TarotStates.waiting_for_dream)
async def dream_process_handler(message: Message, state: FSMContext, db_pool: asyncpg.Pool, bot: Bot):
    user_id = message.from_user.id
    dream_text = message.text
    is_admin = user_id in BOT_ADMIN_IDS

    # Проверка баланса
    price = await check_balance_and_get_price(user_id, "price_dreams", db_pool, bot, message.chat.id)
    if price == -1:
        await send_text(bot, message.chat.id, "Пополните баланс:", reply_markup=get_main_menu_keyboard(is_admin))
        await state.clear()
        return

    loading_msg = await send_loading_animation(bot, message.chat.id, "gifs_dreams", db_pool)

    # Возвращаем главное меню во время ожидания
    # await send_text(bot, message.chat.id, "💤 Погружаюсь в ваше подсознание...",
    #                 reply_markup=get_main_menu_keyboard(is_admin))

    user_repo = UserRepo(db_pool)
    user = await user_repo.get_user(user_id)
    persona_key = user.get("narrative_persona", "default")

    sys_prompt = get_system_prompt(PERSONAS[persona_key]["prompt"])
    user_prompt = make_dream_prompt(dream_text)

    response = await llm_service.generate_response(user_prompt, sys_prompt)

    # 3. УДАЛЯЕМ ГИФКУ
    if loading_msg:
        await delete_message(bot, message.chat.id, loading_msg.message_id)

    if not response:
        await send_text(bot, message.chat.id, "❌ Ошибка толкования. Попробуйте позже.")
        await state.clear()
        return

    # Списание и ответ
    payment_repo = PaymentRepo(db_pool)
    await user_repo.update_user(user_id, karma=user['karma'] - price)
    await payment_repo.add_internal_transaction(user_id, "dream_interpretation", -price)

    await send_text(bot, message.chat.id, response)
    await state.clear()


# ==========================
# 🃏 ТАРО РАСКЛАДЫ
# ==========================
@tarot_router.message(F.text == "🃏 Таро расклады")
@tarot_router.message(Command("tarot"))
async def tarot_menu_handler(message: Message, bot: Bot):
    await send_text(
        bot,
        message.chat.id,
        "🃏 <b>Выберите тип расклада:</b>\n\n"
        "<i>Карта дня — бесплатно раз в сутки.\n"
        "Остальные расклады — за карму.</i>",
        reply_markup=get_tarot_menu_keyboard()
    )



# --- 1. Выбор расклада ---
@tarot_router.callback_query(F.data.startswith("tarot_") & (F.data != "tarot_enter_query") & (F.data != "back_to_main_menu"))
async def tarot_selection_handler(callback: CallbackQuery, state: FSMContext, db_pool: asyncpg.Pool, bot: Bot):
    layout_type = callback.data
    user_id = callback.from_user.id

    configs = {
        "tarot_daily": ("price_daily_tarot", "Карта дня", 1),
        "tarot_one_card": ("price_tarot_one_card", "Одиночная карта", 1),
        "tarot_ppf": ("price_tarot_ppf", "Прошлое, Настоящее, Будущее", 3),
        "tarot_celtic_cross": ("price_tarot_celtic_cross", "Кельтский крест", 10),
        "tarot_intro": ("price_tarot_introduce", "Знакомство с колодой", 3),
        "tarot_transformation": ("price_tarot_transformation", "Личная трансформация", 5),
        "tarot_life_tree": ("price_tarot_life_tree", "Дерево Жизни", 10),
        "tarot_wheel_fate": ("price_tarot_wheel_fate", "Колесо судьбы", 7),
        "tarot_chakra": ("price_tarot_chakra", "Семь чакр", 7),
        "tarot_monthly": ("price_tarot_monthly", "Карта месяца", 1)
    }

    config = configs.get(layout_type)
    if not config:
        await callback.answer("Неизвестный расклад")
        return

    price_key, layout_name, cards_count = config

    # Инициализация Predicts (гарантируем, что запись есть)
    predict_repo = PredictRepo(db_pool)
    predicts = await predict_repo.get_predicts(user_id)
    if not predicts:
        await predict_repo.add_predicts(user_id)
        predicts = {"last_tarot_daily_date": None, "last_tarot_intro_date": None}  # Заглушка для текущего запуска

    today = date.today()

    # ==========================================
    # СЦЕНАРИЙ 1: КАРТА ДНЯ (Бесплатно, 1 раз в сутки, Без вопроса)
    # ==========================================
    if layout_type == "tarot_daily":
        if predicts.get("last_tarot_daily_date") == today:
            await callback.answer("⏳ Вы уже тянули Карту дня сегодня!", show_alert=True)
            return

        await process_tarot_reading(
            user_id, callback.message.chat.id,
            layout_type, layout_name, cards_count,
            "Общий прогноз на сегодня", 0, db_pool, bot
        )
        await predict_repo.update_predicts(user_id, last_tarot_daily_date=today)
        await callback.answer()
        return

    # ==========================================
    # СЦЕНАРИЙ 2: ЗНАКОМСТВО С КОЛОДОЙ (Платно, 1 раз в сутки, Без вопроса)
    # ==========================================
    if layout_type == "tarot_intro":
        # 1. Проверка лимита
        if predicts.get("last_tarot_intro_date") == today:
            await callback.answer("⏳ Вы уже знакомились с колодой сегодня. Приходите завтра!", show_alert=True)
            return

        # 2. Проверка баланса
        price = await check_balance_and_get_price(user_id, price_key, db_pool, bot, callback.message.chat.id)
        if price == -1:
            await callback.answer()
            return

        # 3. Запуск с фиксированным вопросом
        fixed_question = (
            "Проведи интервью с этой колодой Таро. "
            "Расскажи про её характер (1 карта), её сильные стороны (2 карта) "
            "и как нам лучше всего взаимодействовать (3 карта)."
        )

        await process_tarot_reading(
            user_id, callback.message.chat.id,
            layout_type, layout_name, cards_count,
            fixed_question, price, db_pool, bot
        )

        # 4. Обновляем дату intro И общую дату активности
        await predict_repo.update_predicts(user_id, last_tarot_intro_date=today, last_tarot_date=today)
        await callback.answer()
        return

    # ==========================================
    # СЦЕНАРИЙ 3: ОБЫЧНЫЕ РАСКЛАДЫ - Показываем описание
    # ==========================================
    # Проверяем, есть ли информация о раскладе в файле с описаниями
    layout_info = TAROT_LAYOUTS_INFO.get(layout_type)
    if layout_info:
        # Получаем цену расклада из настроек
        settings_repo = SettingsRepo(db_pool)
        setting = await settings_repo.get_setting(layout_info["cost"] if layout_info["cost"] else f"price_{layout_type}")
        if setting:
            price = int(setting["value"]) if setting["value"].isdigit() else 0
            if layout_info["cost"] is None:  # Если стоимость была None, устанавливаем реальную цену
                cost_text = f"{price} ✨"
            else:
                cost_text = layout_info["cost"]
        else:
            cost_text = "0 ✨"

        # Формируем полное описание с ценой в новом формате
        # Разделяем название и описание
        name_part = layout_info["name"]  # Это уже содержит эмодзи и название
        description_part = layout_info["description"]

        full_description = f"<b>{name_part}</b>\n\n<i>{description_part}</i>\n\n<b>Стоимость:</b> {cost_text}"

        # Сохраняем данные расклада в FSM
        await state.update_data(
            layout_type=layout_type,
            layout_name=layout_info["name"],
            price=int(setting["value"]) if setting and setting["value"].isdigit() else 0
        )

        # Для расклада "Знакомство с колодой" используем особую клавиатуру
        if layout_type == "tarot_intro":
            await send_text(
                bot,
                callback.message.chat.id,
                full_description,
                reply_markup=get_tarot_intro_keyboard()
            )
        else:
            await send_text(
                bot,
                callback.message.chat.id,
                full_description,
                reply_markup=get_tarot_request_keyboard()
            )
    else:
        # Если информации об этом раскладе нет в TAROT_LAYOUTS_INFO, используем старую логику
        price = await check_balance_and_get_price(user_id, price_key, db_pool, bot, callback.message.chat.id)
        if price == -1:
            await callback.answer()
            return

        # Сохраняем данные в FSM и просим вопрос
        await state.update_data(
            layout_type=layout_type,
            layout_name=layout_name,
            cards_count=cards_count,
            price=price
        )

        await send_text(
            bot,
            callback.message.chat.id,
            f"🔮 Вы выбрали расклад: <b>{layout_name}</b>\n"
            f"Стоимость: {price} ✨\n\n"
            "Нажмите кнопку ниже, чтобы сформулировать свой вопрос к картам.",
            reply_markup=get_tarot_request_keyboard()
        )
    await callback.answer()


# --- 3. Нажатие "Ввести запрос" (Шаг 3) ---
@tarot_router.callback_query(F.data == "tarot_enter_query")
async def tarot_start_input(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Обработчик кнопки 'Ввести запрос'.
    Переводит бота в режим ожидания текста и показывает кнопку Отмена.
    """
    data = await state.get_data()
    if not data:
        await send_text(bot, callback.message.chat.id, "⚠️ Ошибка данных. Попробуйте выбрать расклад заново.",
                        reply_markup=get_main_menu_keyboard())
        await state.clear()
        return

    await send_text(
        bot,
        callback.message.chat.id,
        f"✍️ <b>Напишите ваш вопрос или опишите ситуацию одним сообщением:</b>\n\n"
        f"Выбранный расклад: <b>{data['layout_name']}</b>\n"
        f"Стоимость: {data['price']} ✨",
        reply_markup=get_cancel_reply_keyboard()
    )
    await state.set_state(TarotStates.waiting_for_question)
    await callback.answer()


# --- 4. Получение вопроса и запуск (Шаг 4) ---
@tarot_router.message(TarotStates.waiting_for_question)
async def tarot_process_handler(message: Message, state: FSMContext, db_pool: asyncpg.Pool, bot: Bot):
    user_id = message.from_user.id
    question = message.text
    data = await state.get_data()

    # Если данных нет (странный сбой или перезагрузка) - сброс
    if not data:
        await send_text(bot, message.chat.id, "⚠️ Ошибка данных. Попробуйте выбрать расклад заново.",
                        reply_markup=get_main_menu_keyboard())
        await state.clear()
        return

    await state.clear()

    # Получаем количество карт для выбранного расклада
    layout_configs = {
        "tarot_daily": 1,
        "tarot_monthly": 1,
        "tarot_one_card": 1,
        "tarot_ppf": 3,
        "tarot_celtic_cross": 10,
        "tarot_intro": 3,
        "tarot_transformation": 5,
        "tarot_life_tree": 10,
        "tarot_wheel_fate": 7,
        "tarot_chakra": 7
    }
    cards_count = layout_configs.get(data['layout_type'], 1)

    # Запускаем процесс
    await process_tarot_reading(
        user_id, message.chat.id,
        data['layout_type'], data['layout_name'], cards_count,
        question, data['price'],
        db_pool, bot
    )


# --- 5. Назад к главному меню ---
@tarot_router.callback_query(F.data == "back_to_main_menu")
async def back_to_main_menu_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    is_admin = callback.from_user.id in BOT_ADMIN_IDS
    await send_text(
        bot,
        callback.message.chat.id,
        "🏠 Вы возвращаетесь в главное меню.",
        reply_markup=get_main_menu_keyboard(is_admin)
    )
    await callback.answer()


# --- 4. ЯДРО ЛОГИКИ РАСКЛАДА ---
async def process_tarot_reading(
        user_id: int, chat_id: int,
        layout_type: str, layout_name: str, count: int,
        question: str, price: int,
        db_pool: asyncpg.Pool, bot: Bot
):
    user_repo = UserRepo(db_pool)
    image_repo = ImageRepo(db_pool)
    payment_repo = PaymentRepo(db_pool)

    # Возвращаем главное меню, убирая кнопку "Отмена"
    is_admin = user_id in BOT_ADMIN_IDS
    main_kb = get_main_menu_keyboard(is_admin)

    # await send_text(bot, chat_id, "🃏 Раскладываю карты... (Это может занять около минуты)", reply_markup=main_kb)

    # Вместо текстового сообщения "Раскладываю карты..." отправляем ГИФКУ
    loading_msg = await send_loading_animation(bot, chat_id, "gifs_tarot", db_pool)

    user = await user_repo.get_user(user_id)
    deck_key = user.get("choice_tarot", "tarot_classic")

    # 1. Тянем карты из БД
    cards = await image_repo.get_random_cards(deck_key, count)
    if not cards:
        await send_text(bot, chat_id,
                        f"❌ Ошибка: не удалось загрузить карты из колоды '{deck_key}'. Обратитесь к админу.")
        return

    # 2. Подготовка информации для ИИ (БЕЗ отправки фото)
    cards_info_for_llm = []

    # Определение позиций для разных раскладов
    positions_ppf = ["Прошлое", "Настоящее", "Будущее"]
    positions_celtic = [
        "Текущая ситуация", "Препятствие/Вызов", "Основа (Прошлое)", "Недавнее прошлое",
        "Возможный исход (Лучшее)", "Ближайшее будущее", "Сам кверент", "Окружение", "Надежды/Страхи", "Итог"
    ]
    positions_transformation = [
        "Текущее Я", "Блокировки", "Скрытые ресурсы", "Направление изменений", "Результат"
    ]
    positions_life_tree = [
        "Корни (прошлое)", "Искусство и творчество", "Общение", "Семья и дом",
        "Самооценка", "Гармония и баланс", "Путь жизни",
        "Влияние духовного", "Интеграция", "Реализация"
    ]
    positions_wheel_fate = [
        "Прошлое", "Настоящее", "Будущее", "Внутренний конфликт",
        "Внешние факторы", "Путь", "Результат"
    ]
    positions_chakra = [
        "Корневая чакра", "Сакральная чакра", "Солнечное сплетение",
        "Сердечная чакра", "Горловая чакра", "Чакра третьего глаза", "Венечная чакра"
    ]

    for i, card in enumerate(cards):
        position_name = f"Позиция {i + 1}"

        # Именования позиций для конкретных раскладов
        if layout_type == "tarot_ppf" and i < 3:
            position_name = positions_ppf[i]
        elif layout_type == "tarot_celtic_cross" and i < 10:
            position_name = positions_celtic[i]
        elif layout_type == "tarot_transformation" and i < 5:
            position_name = positions_transformation[i]
        elif layout_type == "tarot_life_tree" and i < 10:
            position_name = positions_life_tree[i]
        elif layout_type == "tarot_wheel_fate" and i < 7:
            position_name = positions_wheel_fate[i]
        elif layout_type == "tarot_chakra" and i < 7:
            position_name = positions_chakra[i]
        elif layout_type == "tarot_monthly":
            position_name = "Тема Месяца"

        cards_info_for_llm.append(f"{position_name}: {card['ru']} ({card.get('arcana', '')})")

    # 3. ГЕНЕРАЦИЯ LLM (Сначала!)
    persona_key = user.get("narrative_persona", "default")
    sys_prompt = get_system_prompt(PERSONAS[persona_key]["prompt"])
    user_prompt = make_tarot_prompt(layout_name, question, cards_info_for_llm)

    response = await llm_service.generate_response(user_prompt, sys_prompt)

    # 3. УДАЛЯЕМ ГИФКУ
    if loading_msg:
        await delete_message(bot, chat_id, loading_msg.message_id)

    # Если LLM упала — выходим, НЕ отправляем карты, НЕ списываем деньги
    if not response:
        await send_text(bot, chat_id,
                        "❌ Не удалось получить толкование от нейросети. Попробуйте позже (карма не списана).")
        return

        # 4. Успех! Теперь отправляем карты
    media_group = []
    for i, card in enumerate(cards):
        if card['file_id']:
            media = InputMediaPhoto(media=card['file_id'])
        else:
            media = InputMediaPhoto(media=FSInputFile(card['image_path']))

        # Подпись только к первому фото (ограничение телеграм для альбомов)
        if i == 0:
            card_list_str = "\n".join([f"{n + 1}. {c['ru']}" for n, c in enumerate(cards)])
            media.caption = f"<b>{layout_name}</b>\n\n{card_list_str}"
            media.parse_mode = "HTML"
        media_group.append(media)

    sent_messages = []
    try:
        if len(media_group) == 1:
            msg = await send_photo(bot, chat_id, media_group[0].media, caption=media_group[0].caption)
            if msg: sent_messages.append(msg)
        else:
            msgs = await send_media_group(bot, chat_id, media_group)
            if msgs: sent_messages = msgs
    except Exception:
        # Если не удалось отправить фото, отправляем текст с названиями карт
        card_list_str = "\n".join([f"{n + 1}. {c['ru']}" for n, c in enumerate(cards)])
        await send_text(bot, chat_id, f"<b>{layout_name}</b> (Не удалось загрузить изображения)\n\n{card_list_str}")

    # 5. Сохраняем новые file_id (для оптимизации)
    if sent_messages:
        # Для альбома порядок сообщений соответствует порядку в media_group
        for idx, msg_obj in enumerate(sent_messages):
            if idx < len(cards):
                card_record = cards[idx]
                # Если у карты еще нет file_id в БД и в сообщении есть фото
                if not card_record['file_id'] and msg_obj.photo:
                    new_id = msg_obj.photo[-1].file_id
                    await image_repo.update_file_id(card_record['id'], new_id)

    # 6. Отправляем толкование
    await send_text(bot, chat_id, response, reply_markup=main_kb)

    # 7. Списываем карму (ТОЛЬКО СЕЙЧАС)
    if price > 0:
        await user_repo.update_user(user_id, karma=user['karma'] - price)
        await payment_repo.add_internal_transaction(user_id, layout_type, -price)