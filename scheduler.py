import asyncio
import asyncpg
from datetime import date
from aiogram import Bot
from aiogram.types import FSInputFile
from aiogram.enums import ChatMemberStatus
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Импорты проекта
from db import UserRepo, PredictRepo, HoroscopeRepo, PaymentRepo, SettingsRepo, ImageRepo
from services.llm_generator import LLMService
from utils.prompts import get_system_prompt, make_horoscope_prompt
from utils.personas import PERSONAS
from utils.sender import send_text
from utils.helpers import is_premium
from config import LOG_GROUP_ID, CHANNEL_ID_TARO, CHANNEL_ID_MFN


# ============================================================
# 1. ЕЖЕДНЕВНЫЕ БОНУСЫ
# ============================================================
async def daily_bonus_task(bot: Bot, pool: asyncpg.Pool):
    """
    Начисляет карму за Премиум и Подписку на канал.
    """
    logger.info("💰 Запуск раздачи ежедневных бонусов...")

    user_repo = UserRepo(pool)
    payment_repo = PaymentRepo(pool)
    settings_repo = SettingsRepo(pool)

    s_prem = await settings_repo.get_setting("karma_subscription_daily_bonus")
    s_chan = await settings_repo.get_setting("karma_channel_bonus")
    bonus_prem_val = int(s_prem["value"]) if s_prem else 50
    bonus_chan_val = int(s_chan["value"]) if s_chan else 1

    all_users_ids = await user_repo.get_all_user_ids()
    count_users = 0
    total_bonus = 0

    for user_id in all_users_ids:
        user = await user_repo.get_user(user_id)
        if not user: continue

        user_data = dict(user)
        add_karma = 0

        if is_premium(user_data):
            add_karma += bonus_prem_val

        try:
            member = await bot.get_chat_member(CHANNEL_ID_MFN, user_id)
            if member.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
                add_karma += bonus_chan_val
                if not user_data.get('sub_my_freelancer_notes'):
                    await user_repo.update_user(user_id, sub_my_freelancer_notes=True)
            else:
                if user_data.get('sub_my_freelancer_notes'):
                    await user_repo.update_user(user_id, sub_my_freelancer_notes=False)
        except Exception:
            pass

        if add_karma > 0:
            new_karma = await payment_repo.apply_karma_transaction(user_id, "daily_bonus", add_karma)
            if new_karma is not None:
                total_bonus += add_karma
                count_users += 1

        await asyncio.sleep(0.05)

    logger.info(f"✅ Бонусы выданы. Пользователей: {count_users}, Сумма: {total_bonus}")
    await send_text(bot, LOG_GROUP_ID,
                    f"✅ <b>Ежедневные бонусы выданы</b>\nПолучили: {count_users}\nВсего кармы: {total_bonus}")


# ============================================================
# 2. ГЕНЕРАЦИЯ ПЕРСОНАЛЬНЫХ ГОРОСКОПОВ В БД (Ночь)
# ============================================================
async def generate_daily_horoscopes_task(pool: asyncpg.Pool):
    """Ночная генерация подробных гороскопов для бота."""
    logger.info("🌌 Генерация подробных гороскопов для бота...")
    horoscope_repo = HoroscopeRepo(pool)
    llm = LLMService()

    signs = ["овен", "телец", "близнецы", "рак", "лев", "дева",
             "весы", "скорпион", "стрелец", "козерог", "водолей", "рыбы"]

    today = date.today()
    today_str = today.strftime("%d.%m.%Y")
    generated_count = 0

    for sign in signs:
        if await horoscope_repo.get_horoscope(sign, today):
            continue

        prompt = make_horoscope_prompt(sign.capitalize(), today_str)
        sys_prompt = get_system_prompt(PERSONAS["default"]["prompt"])

        content = await llm.generate_response(prompt, sys_prompt)
        if content:
            await horoscope_repo.add_horoscope(sign, today, content)
            generated_count += 1
        else:
            logger.error(f"❌ Ошибка генерации для {sign}")

        await asyncio.sleep(5)

    logger.info(f"✅ Подробные гороскопы сгенерированы: {generated_count}")


# ============================================================
# 3. ПУБЛИКАЦИЯ: КАРТА ДНЯ (Отдельный пост)
# ============================================================
async def post_card_of_the_day_task(bot: Bot, pool: asyncpg.Pool):
    """Публикует Карту Дня в канал."""
    logger.info("📢 Публикация Карты Дня...")
    image_repo = ImageRepo(pool)
    llm = LLMService()

    cards = await image_repo.get_random_cards("tarot_classic", 1)
    if not cards:
        logger.error("Нет карт для публикации в канал!")
        return
    card = cards[0]

    today_str = date.today().strftime("%d.%m.%Y")

    prompt = (
        f"Карта дня на {today_str}: {card['ru']}.\n"
        "Напиши короткий, вдохновляющий прогноз для подписчиков канала (для всех знаков сразу). "
        "Добавь совет дня. Используй эмодзи. Объем до 500 символов."
    )
    sys_prompt = get_system_prompt("Ты — ведущий мистического канала. Твой тон вдохновляющий и легкий.")

    text = await llm.generate_response(prompt, sys_prompt)
    if not text: return

    caption = f"🃏 <b>Карта дня: {card['ru']}</b>\n\n{text}\n\n🔮 <a href='https://t.me/rus_tarot_bot'>Получить личный расклад</a>"

    try:
        if card['file_id']:
            await bot.send_photo(CHANNEL_ID_TARO, card['file_id'], caption=caption)
        else:
            input_file = FSInputFile(card['image_path'])
            msg = await bot.send_photo(CHANNEL_ID_TARO, input_file, caption=caption)
            if msg.photo:
                await image_repo.update_file_id(card['id'], msg.photo[-1].file_id)
        logger.info("✅ Карта дня опубликована.")
    except Exception as e:
        logger.error(f"❌ Ошибка публикации карты дня: {e}")


# ============================================================
# 4. ПУБЛИКАЦИЯ: ГОРОСКОП ДЛЯ КАНАЛА (Генерация с нуля)
# ============================================================
async def post_horoscope_summary_task(bot: Bot, pool: asyncpg.Pool):
    """
    Генерирует НОВЫЙ краткий гороскоп для всех знаков
    и публикует его в канал одним постом.
    """
    logger.info("📢 Генерация и публикация гороскопа для канала...")
    llm = LLMService()

    today_str = date.today().strftime("%d.%m.%Y")

    # Специальный промпт для канала: все знаки, кратко
    prompt = (
        f"Составь краткий гороскоп на сегодня ({today_str}) для всех 12 знаков зодиака. "
        "Формат для каждого знака:\n"
        "'Эмодзи Знак: Прогноз (строго 2-3 предложения)'.\n\n"
        "В начале напиши короткое вступление про общие энергии дня. "
        "Стиль: легкий, позитивный, без лишней воды."
    )

    sys_prompt = get_system_prompt("Ты — популярный астролог, ведущий Telegram-канала.")

    # Увеличиваем токены, так как ответ будет длинным (12 знаков)
    response = await llm.generate_response(prompt, sys_prompt, max_tokens=2500)

    if not response:
        logger.error("❌ Не удалось сгенерировать гороскоп для канала.")
        return

    full_text = f"{response}\n\n🌙 <a href='https://t.me/rus_tarot_bot'>Получить подробный личный гороскоп</a>"

    try:
        # Если текст слишком длинный, разбиваем (хотя краткий должен влезть)
        if len(full_text) > 4096:
            parts = [full_text[i:i + 4096] for i in range(0, len(full_text), 4096)]
            for part in parts:
                await bot.send_message(CHANNEL_ID_TARO, part)
        else:
            await bot.send_message(CHANNEL_ID_TARO, full_text)

        logger.info("✅ Гороскоп для канала опубликован.")
    except Exception as e:
        logger.error(f"❌ Ошибка публикации гороскопа: {e}")


# ============================================================
# 5. ЕЖЕДНЕВНАЯ РАССЫЛКА (Напоминание в ЛС)
# ============================================================
async def daily_reminder_task(bot: Bot, pool: asyncpg.Pool):
    """Рассылает напоминание пользователям."""
    logger.info("⏰ Рассылка утренних напоминаний...")
    user_repo = UserRepo(pool)
    predict_repo = PredictRepo(pool)

    users = await user_repo.get_all_user_ids()
    today = date.today()
    count = 0

    text = (
        "☀️ <b>Доброе утро!</b>\n\n"
        "Звезды уже выстроились в ряд, а карты готовы открыть тайны грядущего дня.\n\n"
        "☕️ Не забудьте:\n"
        "✨ Прочитать /horoscope\n"
        "🃏 Узнать Карту Дня (бесплатно)\n"
        "💤 Узнать значение сна\n\n"
        "<i>Желаем волшебного дня!</i>"
    )

    for user_id in users:
        user = await user_repo.get_user(user_id)
        if not user or not user.get('can_send_msg', True):
            continue

        predicts = await predict_repo.get_predicts(user_id)
        # Если пользователь уже что-то делал сегодня (получил гороскоп ИЛИ карту), не беспокоим
        horoscope_done = predicts and predicts.get('last_horoscope_daily_date') == today
        tarot_done = predicts and predicts.get('last_tarot_daily_date') == today

        if horoscope_done or tarot_done:
            continue

        try:
            await send_text(bot, user_id, text)
            count += 1
        except Exception:
            await user_repo.update_user(user_id, can_send_msg=False)

        await asyncio.sleep(0.05)

    logger.info(f"✅ Напоминание отправлено {count} пользователям.")


# ============================================================
# ⚙️ НАСТРОЙКА ПЛАНИРОВЩИКА
# ============================================================
def setup_scheduler(bot: Bot, pool: asyncpg.Pool) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    # 1. Генерация подробных гороскопов в БД (3:00 ночи)
    scheduler.add_job(
        generate_daily_horoscopes_task,
        CronTrigger(hour=3, minute=0),
        args=[pool]
    )

    # 2. Пост "Карта дня" в канал (8:00 утра)
    scheduler.add_job(
        post_card_of_the_day_task,
        CronTrigger(hour=8, minute=0),
        args=[bot, pool]
    )

    # 3. Пост "Гороскоп для всех" в канал (8:30 утра)
    scheduler.add_job(
        post_horoscope_summary_task,
        CronTrigger(hour=8, minute=30),
        args=[bot, pool]
    )

    # 4. Начисление бонусов (8:15 утра)
    scheduler.add_job(
        daily_bonus_task,
        CronTrigger(hour=8, minute=15),
        args=[bot, pool]
    )

    # 5. Напоминание пользователям (9:00 утра)
    scheduler.add_job(
        daily_reminder_task,
        CronTrigger(hour=8, minute=1),
        args=[bot, pool]
    )

    return scheduler
