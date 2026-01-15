# config.py
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

# --- Настройки Бота ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Преобразуем строку ID админов в список целых чисел
admin_ids_str = os.getenv("BOT_ADMIN_IDS", "")
try:
    BOT_ADMIN_IDS = list(map(int, admin_ids_str.split(','))) if admin_ids_str else []
except ValueError:
    print("Ошибка: BOT_ADMIN_IDS в .env содержит нечисловые значения.")
    BOT_ADMIN_IDS = []

# ID групп и каналов
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", 0))
CHANNEL_ID_TARO = int(os.getenv("CHANNEL_ID_TARO", 0))
CHANNEL_ID_MFN = int(os.getenv("CHANNEL_ID_MFN", 0))

# --- Настройки LLM: SambaNova ---
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY")
SAMBANOVA_MODEL = os.getenv("SAMBANOVA_MODEL")

# --- Настройки PostgreSQL ---
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = int(os.getenv("DB_PORT", 5432))

# --- Настройки ЮKassa (YooKassa) ---
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
