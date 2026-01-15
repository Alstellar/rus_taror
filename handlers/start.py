# handlers/start.py
import asyncpg
from aiogram import Router, Bot, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message
from aiogram.enums import ChatMemberStatus

from config import LOG_GROUP_ID, BOT_ADMIN_IDS, CHANNEL_ID_MFN
from db import UserRepo
from utils.sender import send_text
from keyboards.reply_kb import get_main_menu_keyboard

start_router = Router()


@start_router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, bot: Bot, db_pool: asyncpg.Pool):
    """
    Обработчик команды /start.
    Регистрирует пользователя, проверяет рефералов и подписку.
    """
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    # Инициализируем репозиторий
    user_repo = UserRepo(db_pool)

    # 1. Проверяем, есть ли пользователь в БД
    existing_user = await user_repo.get_user(user_id)
    is_new_user = existing_user is None

    # 2. Обработка реферальной системы (только для новых)
    id_referrer = 0
    if is_new_user:
        args = command.args  # Получаем аргументы после /start (например, ref_12345)
        if args and args.startswith("ref_"):
            try:
                possible_referrer = int(args.split("_")[1])
                # Нельзя быть рефералом самого себя
                if possible_referrer != user_id:
                    # Проверяем, существует ли такой реферер
                    ref_user = await user_repo.get_user(possible_referrer)
                    if ref_user:
                        id_referrer = possible_referrer
            except (ValueError, IndexError):
                pass

        # 3. Регистрируем пользователя
        await user_repo.add_user(
            user_id=user_id,
            username=username,
            id_referrer=id_referrer
        )

        # 4. Проверяем подписку на канал (MFN) при старте для бонуса
        try:
            member = await bot.get_chat_member(CHANNEL_ID_MFN, user_id)
            is_sub = member.status in (
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.CREATOR
            )
            # Обновляем статус подписки в БД
            await user_repo.update_user(user_id, sub_my_freelancer_notes=is_sub)
        except Exception:
            pass  # Если бот не админ канала или ошибка API, просто пропускаем

        # 5. Логируем новую регистрацию в чат логов
        log_text = (
            f"👶 <b>Новый пользователь!</b>\n"
            f"ID: <code>{user_id}</code>\n"
            f"Имя: {first_name}\n"
            f"Username: @{username if username else 'нет'}\n"
            f"Реферер: <code>{id_referrer}</code>"
        )
        await send_text(bot, LOG_GROUP_ID, log_text)

    # 6. Отправляем приветствие и меню
    is_admin = user_id in BOT_ADMIN_IDS
    kb = get_main_menu_keyboard(is_admin)

    welcome_text = (
        f"Привет, {first_name}! 👋\n\n"
        "Я — твой проводник в мир Таро и Астрологии. ✨\n"
        "Я помогу тебе разобраться в себе, получить совет карт или узнать, что сулят звезды.\n\n"
        "<b>Доступные разделы:</b>\n"
        "🔮 <b>Таро расклады</b> — ответы на твои вопросы\n"
        "🌙 <b>Гороскоп</b> — ежедневный прогноз\n"
        "💤 <b>Сонник</b> — толкование сновидений\n\n"
        "👇 <i>Воспользуйся меню внизу для навигации</i>"
    )

    await send_text(bot, user_id, welcome_text, reply_markup=kb)