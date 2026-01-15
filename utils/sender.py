# utils/sender.py
import asyncio
from typing import Union, List, Optional
from aiogram import Bot
from aiogram.types import Message, InputMediaPhoto, ReplyKeyboardMarkup, InlineKeyboardMarkup, URLInputFile, FSInputFile
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramAPIError
from loguru import logger

from db import ImageRepo
import asyncpg


async def send_text(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Union[ReplyKeyboardMarkup, InlineKeyboardMarkup, None] = None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True
) -> Optional[Message]:
    """Безопасная отправка текстового сообщения."""
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
    except TelegramForbiddenError:
        logger.warning(f"🚫 Пользователь {chat_id} заблокировал бота.")
    except TelegramRetryAfter as e:
        logger.warning(f"⏳ Flood limit для {chat_id}. Ждем {e.retry_after} сек.")
        await asyncio.sleep(e.retry_after)
        return await send_text(bot, chat_id, text, reply_markup, parse_mode, disable_web_page_preview)
    except TelegramAPIError as e:
        logger.error(f"❌ Ошибка API при отправке текста {chat_id}: {e}")
    except Exception as e:
        logger.exception(f"❌ Неизвестная ошибка при отправке текста {chat_id}: {e}")
    return None

async def send_photo(
    bot: Bot,
    chat_id: int,
    photo: Union[str, FSInputFile, URLInputFile],
    caption: str = None,
    reply_markup: Union[ReplyKeyboardMarkup, InlineKeyboardMarkup, None] = None,
    parse_mode: str = "HTML"
) -> Optional[Message]:
    """Безопасная отправка фото."""
    try:
        return await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except TelegramForbiddenError:
        logger.warning(f"🚫 Пользователь {chat_id} заблокировал бота (фото).")
    except TelegramAPIError as e:
        logger.error(f"❌ Ошибка API при отправке фото {chat_id}: {e}")
    return None

async def send_media_group(
    bot: Bot,
    chat_id: int,
    media: List[InputMediaPhoto]
) -> Optional[List[Message]]:
    """Безопасная отправка альбома."""
    try:
        return await bot.send_media_group(chat_id=chat_id, media=media)
    except TelegramAPIError as e:
        logger.error(f"❌ Ошибка отправки альбома {chat_id}: {e}")
    return None

async def edit_text(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: Union[InlineKeyboardMarkup, None] = None,
    parse_mode: str = "HTML"
) -> Optional[Message]:
    """Безопасное редактирование текста."""
    try:
        return await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except TelegramAPIError as e:
        # Часто бывает "Message is not modified", это не критично
        if "message is not modified" not in str(e).lower():
            logger.error(f"❌ Ошибка редактирования {chat_id}/{message_id}: {e}")
    return None

async def delete_message(bot: Bot, chat_id: int, message_id: int) -> bool:
    """Безопасное удаление сообщения."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except TelegramAPIError:
        return False



async def send_loading_animation(
        bot: Bot,
        chat_id: int,
        dict_name: str,
        db_pool: asyncpg.Pool
) -> Optional[Message]:
    """
    Выбирает случайную гифку из указанной категории (dict_name) и отправляет её.
    Возвращает объект сообщения (чтобы потом его удалить).
    """
    repo = ImageRepo(db_pool)

    # Используем существующий метод get_random_cards, он универсален
    records = await repo.get_random_cards(dict_name, 1)

    if not records:
        # Если гифок нет, отправляем текстовое уведомление
        return await send_text(bot, chat_id, "⏳ <i>Ожидаю ответа от Вселенной...</i>")

    gif = records[0]

    try:
        msg = None
        # Если есть file_id - шлем по ID
        if gif['file_id']:
            msg = await bot.send_animation(chat_id, animation=gif['file_id'])
        else:
            # Если нет - шлем файлом и сохраняем ID
            input_file = FSInputFile(gif['image_path'])
            msg = await bot.send_animation(chat_id, animation=input_file)

            if msg.animation:
                await repo.update_file_id(gif['id'], msg.animation.file_id)

        return msg

    except Exception as e:
        logger.error(f"Ошибка отправки GIF: {e}")
        return await send_text(bot, chat_id, "<i>Ожидаю ответа от Вселенной... ⏳</i>")