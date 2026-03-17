import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# --- bootstrap optional dependency: asyncpg ---
if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")

    class _DummyPool:
        pass

    asyncpg_stub.Pool = _DummyPool
    asyncpg_stub.Record = dict
    sys.modules["asyncpg"] = asyncpg_stub

# --- bootstrap optional dependency: loguru ---
if "loguru" not in sys.modules:
    loguru_stub = types.ModuleType("loguru")

    class _DummyLogger:
        def __getattr__(self, name):
            def _noop(*args, **kwargs):
                return None
            return _noop

    loguru_stub.logger = _DummyLogger()
    sys.modules["loguru"] = loguru_stub

# --- bootstrap optional dependency: aiogram ---
if "aiogram" not in sys.modules:
    aiogram_stub = types.ModuleType("aiogram")

    class _DummyBot:
        pass

    aiogram_stub.Bot = _DummyBot

    aiogram_types_stub = types.ModuleType("aiogram.types")
    for cls_name in [
        "Message",
        "InputMediaPhoto",
        "ReplyKeyboardMarkup",
        "InlineKeyboardMarkup",
        "URLInputFile",
        "FSInputFile",
    ]:
        setattr(aiogram_types_stub, cls_name, type(cls_name, (), {}))

    aiogram_exceptions_stub = types.ModuleType("aiogram.exceptions")

    class _DummyTelegramError(Exception):
        pass

    class _DummyRetryAfter(_DummyTelegramError):
        retry_after = 0

    aiogram_exceptions_stub.TelegramForbiddenError = _DummyTelegramError
    aiogram_exceptions_stub.TelegramRetryAfter = _DummyRetryAfter
    aiogram_exceptions_stub.TelegramAPIError = _DummyTelegramError

    sys.modules["aiogram"] = aiogram_stub
    sys.modules["aiogram.types"] = aiogram_types_stub
    sys.modules["aiogram.exceptions"] = aiogram_exceptions_stub

import utils.sender as sender_module


class SenderTests(unittest.IsolatedAsyncioTestCase):
    async def test_html_fallback_to_plain_text_on_api_error(self):
        class FakeBot:
            def __init__(self):
                self.parse_modes = []

            async def send_message(self, **kwargs):
                self.parse_modes.append(kwargs.get("parse_mode"))
                if kwargs.get("parse_mode") == "HTML":
                    raise Exception("can't parse entities")
                return SimpleNamespace(message_id=1)

        bot = FakeBot()

        with patch.object(sender_module, "TelegramAPIError", Exception):
            msg = await sender_module.send_text(
                bot=bot,
                chat_id=1,
                text="<b>Hello</b>",
                parse_mode="HTML",
            )

        self.assertIsNotNone(msg)
        self.assertEqual(bot.parse_modes, ["HTML", None])

    async def test_long_text_is_split_into_multiple_messages(self):
        sent_chunks = []

        class FakeBot:
            async def send_message(self, **kwargs):
                sent_chunks.append(kwargs["text"])
                return SimpleNamespace(message_id=len(sent_chunks))

        bot = FakeBot()
        long_text = "A" * (sender_module.SAFE_TEXT_CHUNK * 2 + 10)

        msg = await sender_module.send_text(bot=bot, chat_id=1, text=long_text, parse_mode=None)

        self.assertIsNotNone(msg)
        self.assertGreaterEqual(len(sent_chunks), 3)


if __name__ == "__main__":
    unittest.main()
