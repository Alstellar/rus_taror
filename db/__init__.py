# db/__init__.py

from .users import UserRepo
from .predicts import PredictRepo
from .payments import PaymentRepo
from .settings import SettingsRepo
from .bot_images import ImageRepo
from .daily_horoscope import HoroscopeRepo
from .tables import create_tables

__all__ = [
    "UserRepo",
    "PredictRepo",
    "PaymentRepo",
    "SettingsRepo",
    "ImageRepo",
    "HoroscopeRepo",
    "create_tables",
]