# utils/sender.py
import asyncio
import re
from typing import Union, List, Optional

import asyncpg
from aiogram import Bot
from aiogram.types import (
    Message,
    InputMediaPhoto,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    URLInputFile,
    FSInputFile,
)
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramAPIError
from loguru import logger

from db import ImageRepo

TELEGRAM_MESSAGE_LIMIT = 4096
SAFE_TEXT_CHUNK = 3900


def _strip_html_tags(text: str) -> str:
    """Удаляет HTML-теги для безопасного fallback-режима plain text."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def _split_text(text: str, max_len: int = SAFE_TEXT_CHUNK) -> List[str]:
    """Разбивает длинный текст на части, стараясь резать по переносам строк."""
    if len(text) <= max_len:
        return [text]

    chunks: List[str] = []
    rest = text
    while len(rest) > max_len:
        split_pos = rest.rfind("\n", 0, max_len)
        if split_pos <= 0:
            split_pos = max_len
        chunks.append(rest[:split_pos].strip())
        rest = rest[split_pos:].strip()
    if rest:
        chunks.append(rest)
    return chunks


async def send_text(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Union[ReplyKeyboardMarkup, InlineKeyboardMarkup, None] = None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
    **kwargs,
) -> Optional[Message]:
    """Безопасная отправка текстового сообщения."""
    if not text:
        logger.warning(f"Пустой текст для отправки в чат {chat_id}.")
        return None

    mode = parse_mode
    prepared_text = text

    # Для очень длинного HTML-текста отправляем plain text, чтобы не ломать теги на границах.
    if mode == "HTML" and len(prepared_text) > TELEGRAM_MESSAGE_LIMIT:
        logger.warning(f"Длинный HTML-текст в чат {chat_id}: переключаемся в plain text.")
        prepared_text = _strip_html_tags(prepared_text)
        mode = None

    chunks = _split_text(prepared_text)
    sent_msg: Optional[Message] = None

    try:
        for idx, chunk in enumerate(chunks):
            chunk_reply_markup = reply_markup if idx == len(chunks) - 1 else None
            sent_msg = await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                reply_markup=chunk_reply_markup,
                parse_mode=mode,
                disable_web_page_preview=disable_web_page_preview,
                **kwargs,
            )
        return sent_msg
    except TelegramForbiddenError:
        logger.warning(f"🚫 Пользователь {chat_id} заблокировал бота.")
    except TelegramRetryAfter as e:
        logger.warning(f"⏳ Flood limit для {chat_id}. Ждем {e.retry_after} сек.")
        await asyncio.sleep(e.retry_after + 0.1)
        return await send_text(
            bot=bot,
            chat_id=chat_id,
            text=prepared_text,
            reply_markup=reply_markup,
            parse_mode=mode,
            disable_web_page_preview=disable_web_page_preview,
            **kwargs,
        )
    except TelegramAPIError as e:
        if mode == "HTML":
            logger.warning(f"⚠️ Ошибка HTML в чате {chat_id}, пробуем plain text fallback: {e}")
            plain_chunks = _split_text(_strip_html_tags(prepared_text))
            try:
                for idx, chunk in enumerate(plain_chunks):
                    chunk_reply_markup = reply_markup if idx == len(plain_chunks) - 1 else None
                    sent_msg = await bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        reply_markup=chunk_reply_markup,
                        parse_mode=None,
                        disable_web_page_preview=disable_web_page_preview,
                        **kwargs,
                    )
                return sent_msg
            except TelegramAPIError as fallback_error:
                logger.error(f"❌ Ошибка API при fallback-отправке текста {chat_id}: {fallback_error}")
        else:
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
    parse_mode: str = "HTML",
) -> Optional[Message]:
    """Безопасная отправка фото."""
    try:
        return await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except TelegramForbiddenError:
        logger.warning(f"🚫 Пользователь {chat_id} заблокировал бота (фото).")
    except TelegramAPIError as e:
        logger.error(f"❌ Ошибка API при отправке фото {chat_id}: {e}")
    return None


async def send_media_group(
    bot: Bot,
    chat_id: int,
    media: List[InputMediaPhoto],
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
    parse_mode: str = "HTML",
) -> Optional[Message]:
    """Безопасное редактирование текста."""
    try:
        return await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except TelegramAPIError as e:
        if "message is not modified" in str(e).lower():
            return None

        if parse_mode == "HTML":
            plain = _strip_html_tags(text)[:TELEGRAM_MESSAGE_LIMIT]
            try:
                return await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=plain,
                    reply_markup=reply_markup,
                    parse_mode=None,
                )
            except TelegramAPIError as fallback_error:
                logger.error(f"❌ Ошибка fallback-редактирования {chat_id}/{message_id}: {fallback_error}")
        else:
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
    db_pool: asyncpg.Pool,
) -> Optional[Message]:
    """
    Выбирает случайную гифку из указанной категории (dict_name) и отправляет её.
    Возвращает объект сообщения (чтобы потом его удалить).
    """
    repo = ImageRepo(db_pool)

    records = await repo.get_random_cards(dict_name, 1)

    if not records:
        return await send_text(bot, chat_id, "⏳ <i>Ожидаю ответа от Вселенной...</i>")

    gif = records[0]

    try:
        msg = None
        if gif["file_id"]:
            msg = await bot.send_animation(chat_id, animation=gif["file_id"])
        else:
            input_file = FSInputFile(gif["image_path"])
            msg = await bot.send_animation(chat_id, animation=input_file)

            if msg.animation:
                await repo.update_file_id(gif["id"], msg.animation.file_id)

        return msg

    except Exception as e:
        logger.error(f"Ошибка отправки GIF: {e}")
        return await send_text(bot, chat_id, "<i>Ожидаю ответа от Вселенной... ⏳</i>")
