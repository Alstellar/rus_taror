# utils/helpers.py
from datetime import date, datetime
from typing import Optional, Dict, Any


def get_zodiac_sign(d: date) -> str:
    """Определяет знак зодиака и возвращает его с эмодзи."""
    day, month = d.day, d.month

    if (month == 12 and day >= 22) or (month == 1 and day <= 19):
        return "Козерог ♑"
    elif (month == 1 and day >= 20) or (month == 2 and day <= 18):
        return "Водолей ♒"
    elif (month == 2 and day >= 19) or (month == 3 and day <= 20):
        return "Рыбы ♓"
    elif (month == 3 and day >= 21) or (month == 4 and day <= 19):
        return "Овен ♈"
    elif (month == 4 and day >= 20) or (month == 5 and day <= 20):
        return "Телец ♉"
    elif (month == 5 and day >= 21) or (month == 6 and day <= 20):
        return "Близнецы ♊"
    elif (month == 6 and day >= 21) or (month == 7 and day <= 22):
        return "Рак ♋"
    elif (month == 7 and day >= 23) or (month == 8 and day <= 22):
        return "Лев ♌"
    elif (month == 8 and day >= 23) or (month == 9 and day <= 22):
        return "Дева ♍"
    elif (month == 9 and day >= 23) or (month == 10 and day <= 22):
        return "Весы ♎"
    elif (month == 10 and day >= 23) or (month == 11 and day <= 21):
        return "Скорпион ♏"
    elif (month == 11 and day >= 22) or (month == 12 and day <= 21):
        return "Стрелец ♐"
    return "Неизвестно ❓"


def is_premium(user_record: Dict[str, Any]) -> bool:
    """
    Проверяет наличие активной премиум-подписки.
    Принимает словарь данных пользователя или объект Record.
    """
    if not user_record:
        return False

    prem_date = user_record.get("premium_date")

    # Если даты нет или она None
    if not prem_date:
        return False

    # Сравниваем с текущим временем
    if prem_date > datetime.now():
        return True

    return False