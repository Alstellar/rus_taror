from typing import Any, Awaitable, Callable, Dict

import asyncpg
from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject

from db import UserRepo
from utils.sender import send_text


BOT_URL = "https://t.me/rus_tarot_bot"
GROUP_NOTICE = (
    "⚠️ Этот бот работает только в личном диалоге.\n\n"
    "Перейдите в бот и отправьте команду /start, чтобы начать пользоваться им:\n"
    f"<a href=\"{BOT_URL}\">@rus_tarot_bot</a>"
)
START_NOTICE = "👋 Сначала запустите бота командой /start."
GROUP_ACTIONS = {
    "👤 Профиль", "🌙 Гороскоп", "🃏 Таро расклады", "💤 Сонник",
    "🏪 Маркетплейс", "📌 Наши проекты", "ℹ️ Инфо", "📜 Оферта и условия",
}


class PrivateRegisteredUserMiddleware(BaseMiddleware):
    """Allows bot scenarios only in private chats for users known to the database."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        message = event if isinstance(event, Message) else None
        callback = event if isinstance(event, CallbackQuery) else None
        chat = message.chat if message else (callback.message.chat if callback and callback.message else None)
        user = message.from_user if message else (callback.from_user if callback else None)

        if not chat or not user or user.is_bot:
            return await handler(event, data)

        if chat.type != ChatType.PRIVATE:
            # Do not react to unrelated group conversation. Commands and callbacks are bot actions.
            is_command = bool(
                message and message.text
                and (message.text.startswith("/") or message.text in GROUP_ACTIONS)
            )
            if callback:
                await callback.answer("Бот работает только в личном диалоге.", show_alert=True)
                await chat_answer(callback.message, GROUP_NOTICE)
            elif is_command:
                await chat_answer(message, GROUP_NOTICE)
            return None

        is_start = bool(message and message.text and message.text.startswith("/start"))
        if is_start:
            return await handler(event, data)

        if not await UserRepo(self.pool).get_user(user.id):
            if callback:
                await callback.answer("Сначала отправьте /start.", show_alert=True)
            await send_text(data["bot"], chat.id, START_NOTICE)
            return None

        return await handler(event, data)


async def chat_answer(message: Message, text: str) -> None:
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
