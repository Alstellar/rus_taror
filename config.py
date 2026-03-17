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

# --- Настройки LLM: OpenRouter ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-4-maverick")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_FALLBACK_MODELS = [
    model.strip() for model in os.getenv(
        "OPENROUTER_FALLBACK_MODELS",
        "meta-llama/llama-4-scout,qwen/qwen-2.5-72b-instruct"
    ).split(",")
    if model.strip()
]

# --- Настройки PostgreSQL ---
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = int(os.getenv("DB_PORT", 5432))

# --- Настройки ЮKassa (YooKassa) ---
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
