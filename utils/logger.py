# utils/logger.py
import logging
import sys
from loguru import logger


class InterceptHandler(logging.Handler):
    """
    Перехватчик стандартных логов Python (например, от aiogram или asyncpg)
    и перенаправление их в loguru.
    """

    def emit(self, record):
        # Получаем соответствующий уровень логирования loguru
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Находим, откуда был вызван лог
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logger():
    """
    Настройка конфигурации логгера:
    1. Удаляет стандартный обработчик.
    2. Настраивает вывод в консоль (цветной).
    3. Настраивает вывод в файл с ротацией и сжатием.
    4. Перехватывает системные логи библиотек.
    """
    # Удаляем дефолтный обработчик, чтобы не дублировались сообщения
    logger.remove()

    # 1. Вывод в консоль (для Docker logs / отладки)
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

    # 2. Вывод в файл (с ротацией и хранением 7 дней)
    logger.add(
        "logs/bot.log",
        rotation="00:00",  # Новый файл создается каждый день в полночь
        retention="7 days",  # Храним логи за последние 7 дней
        compression="zip",  # Сжимаем старые логи в zip-архив для экономии места
        level="INFO",
        encoding="utf-8",
        enqueue=True,  # Асинхронная и безопасная запись в файл
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )

    # 3. Настройка перехвата стандартных логов (aiogram, asyncpg и др.)
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Устанавливаем уровень INFO для aiogram и asyncpg, чтобы не спамили DEBUG-ом
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("asyncpg").setLevel(logging.INFO)