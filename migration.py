import asyncio
import csv
import os
import asyncpg
from datetime import datetime
from dotenv import load_dotenv

# Загружаем настройки
load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

CSV_FILE = "users.csv"


def clean_val(val):
    """
    Очищает значение из CSV:
    - Если это 'NULL', возвращает None.
    - Если пустая строка, возвращает None.
    - Иначе возвращает строку.
    """
    if val is None:
        return None
    v = val.strip()
    if v == '' or v.upper() == 'NULL':
        return None
    return v


async def migrate_users():
    print(f"🔌 Подключение к БД {DB_NAME}...")
    try:
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return

    print(f"📂 Чтение файла {CSV_FILE}...")

    if not os.path.exists(CSV_FILE):
        print(f"❌ Файл {CSV_FILE} не найден!")
        return

    success_count = 0
    skip_count = 0
    error_count = 0

    with open(CSV_FILE, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            user_id_raw = row.get('user_id')

            try:
                # 1. Очистка и подготовка данных
                user_id = int(user_id_raw)

                # Username
                username = clean_val(row.get('username'))

                # Karma (если NULL или мусор -> 50)
                karma_raw = clean_val(row.get('karma'))
                karma = int(karma_raw) if karma_raw else 50

                # Дата рождения (Date)
                dob_raw = clean_val(row.get('added_date_of_birth'))
                dob = None
                if dob_raw:
                    # Пробуем разные форматы на всякий случай
                    try:
                        dob = datetime.strptime(dob_raw, '%Y-%m-%d').date()
                    except ValueError:
                        pass  # Если формат кривой, оставим None

                # Премиум дата (Timestamp)
                prem_raw = clean_val(row.get('premium_date'))
                premium_date = None
                if prem_raw:
                    try:
                        # Заменяем пробел на T для корректного isoformat, если нужно
                        prem_raw = prem_raw.replace(' ', 'T')
                        premium_date = datetime.fromisoformat(prem_raw)
                    except ValueError:
                        pass

                # Дата регистрации (Timestamp)
                reg_raw = clean_val(row.get('registration_date'))
                reg_date = datetime.now()
                if reg_raw:
                    try:
                        reg_raw = reg_raw.replace(' ', 'T')
                        reg_date = datetime.fromisoformat(reg_raw)
                    except ValueError:
                        pass

                # 2. Вставка в БД
                query = """
                        INSERT INTO users (user_id, \
                                           username, \
                                           karma, \
                                           added_date_of_birth, \
                                           premium_date, \
                                           registration_date)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (user_id) DO NOTHING; \
                        """

                res = await conn.execute(query, user_id, username, karma, dob, premium_date, reg_date)

                if res == "INSERT 0 1":
                    success_count += 1
                else:
                    skip_count += 1

            except Exception as e:
                error_count += 1
                print(f"⚠️ Ошибка для ID {user_id_raw}: {e}")

    await conn.close()

    print("-" * 30)
    print("✅ Миграция завершена!")
    print(f"➕ Добавлено: {success_count}")
    print(f"⏭ Пропущено (дубликаты): {skip_count}")
    print(f"❌ Ошибки: {error_count}")


if __name__ == "__main__":
    asyncio.run(migrate_users())