# Rus Tarot Bot

Telegram-бот для гадания на картах Таро, получения гороскопов и толкования снов.

## Установка

1. Склонируйте репозиторий:
```bash
git clone https://github.com/yourusername/rus_tarot_bot.git
cd rus_tarot_bot
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл `.env` на основе шаблона `.env.example`:
```bash
cp .env.example .env
```

4. Заполните `.env` своими данными:
   - `BOT_TOKEN` - токен бота от [@BotFather](https://t.me/BotFather)
   - `OPENROUTER_API_KEY` - API-ключ для OpenRouter
   - `OPENROUTER_MODEL` - основная модель в формате `provider/model` (например, `meta-llama/llama-4-maverick`)
   - `OPENROUTER_FALLBACK_MODELS` - запасные модели через запятую (если основная недоступна)
   - `DB_PASSWORD` - пароль от базы данных PostgreSQL
   - Прочие настройки по необходимости

5. Запустите бота:
```bash
python main.py
```

## Структура проекта

- `main.py` - основной файл запуска бота
- `config.py` - конфигурация проекта
- `handlers/` - обработчики команд бота
- `db/` - работа с базой данных
- `services/` - сервисы (например, генератор LLM)
- `utils/` - вспомогательные утилиты
- `keyboards/` - inline и reply клавиатуры

## Особенности

- Интеграция с OpenRouter для генерации интерпретации карт Таро
- Автоматические рассылки и напоминания
- Поддержка гороскопов и сонника
- Встроенная система платежей через ЮKassa
- Реферальная система
