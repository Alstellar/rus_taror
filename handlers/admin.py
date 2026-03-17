import asyncpg
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from config import BOT_ADMIN_IDS
from db import UserRepo, SettingsRepo, PaymentRepo
from services.media_loader import MediaLoaderService
from utils.sender import send_text, delete_message, edit_text
from keyboards.inline_kb import get_admin_main_keyboard, get_confirm_broadcast_keyboard, get_cancel_keyboard
from keyboards.reply_kb import get_cancel_reply_keyboard, get_main_menu_keyboard

# Инициализация роутера и фильтра на админов
admin_router = Router()
admin_router.message.filter(F.from_user.id.in_(BOT_ADMIN_IDS))


# Состояния для FSM (Рассылка)
class AdminStates(StatesGroup):
    waiting_for_broadcast_msg = State()
    waiting_for_user_id = State()


# ==========================================================
# ⚙️ ГЛАВНОЕ МЕНЮ АДМИНКИ
# ==========================================================

@admin_router.message(Command("admin"))
@admin_router.message(F.text == "⚙️ Админ-панель")
async def admin_panel_handler(message: Message, bot: Bot):
    uid = message.from_user.id

    text = (
        "⚙️ <b>Панель Администратора</b>\n\n"
        "<b>📋 Быстрые команды:</b>\n\n"
        "🔹 <b>Выдать карму:</b>\n"
        f"<code>/add_karma {uid} 100</code>\n"
        f"<code>/add_karma {uid} 500</code>\n\n"
        "🔹 <b>Выдать подписку (дни):</b>\n"
        f"<code>/add_premium {uid} 30</code>\n"
        f"<code>/add_premium {uid} 365</code>\n\n"
        "🔹 <b>Загрузка картинок:</b>\n"
        "<code>/read_folder tarot_classic</code>\n"
        "<code>/read_folder tarot_black_cat</code>\n"
        "<code>/read_folder bot_images</code>\n\n"
        "🔹 <b>Загрузка gif:</b>\n"
        "<code>/read_folder gifs_astro</code>\n"
        "<code>/read_folder gifs_dreams</code>\n"
        "<code>/read_folder gifs_tarot</code>\n\n"
        "🔹 <b>Настройки:</b>\n"
        "<code>/prices</code> — Показать и изменить цены\n\n"
        "👇 <b>Управление рассылками:</b>"
    )
    await send_text(bot, message.chat.id, text, reply_markup=get_admin_main_keyboard())


# ==========================================================
# 🛠 БАЗОВЫЕ КОМАНДЫ
# ==========================================================

# --- 1. Загрузка картинок ---
@admin_router.message(Command("read_folder"))
async def cmd_read_folder(message: Message, command: CommandObject, db_pool: asyncpg.Pool, bot: Bot):
    folder_name = command.args
    if not folder_name:
        await send_text(bot, message.chat.id, "⚠️ Укажите имя папки.\nПример: <code>/read_folder tarot_classic</code>")
        return

    await send_text(bot, message.chat.id, f"📂 Начинаю сканирование папки <b>{folder_name}</b>...")

    loader = MediaLoaderService(db_pool)
    try:
        await loader.scan_and_load_folder(folder_name)
        await send_text(bot, message.chat.id, f"✅ Папка <b>{folder_name}</b> успешно обработана.")
    except Exception as e:
        await send_text(bot, message.chat.id, f"❌ Ошибка при сканировании: {e}")


# --- 2. Выдача Кармы ---
@admin_router.message(Command("add_karma"))
async def cmd_add_karma(message: Message, command: CommandObject, db_pool: asyncpg.Pool, bot: Bot):
    args = command.args.split() if command.args else []
    if len(args) != 2:
        await send_text(bot, message.chat.id, "⚠️ Формат: <code>/add_karma user_id amount</code>")
        return

    try:
        target_user_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await send_text(bot, message.chat.id, "⚠️ ID и сумма должны быть числами.")
        return

    user_repo = UserRepo(db_pool)
    payment_repo = PaymentRepo(db_pool)

    user = await user_repo.get_user(target_user_id)
    if not user:
        await send_text(bot, message.chat.id, "❌ Пользователь не найден в БД.")
        return

    new_karma = await payment_repo.apply_karma_transaction(target_user_id, "admin_gift", amount)
    if new_karma is None:
        await send_text(bot, message.chat.id, "❌ Не удалось применить изменение кармы (возможно, недостаточно средств).")
        return

    await send_text(bot, message.chat.id, f"✅ Пользователю <code>{target_user_id}</code> начислено {amount} кармы.")
    await send_text(bot, target_user_id,
                    f"🎁 <b>Вам начислено {amount} кармы от администратора!</b>\nТекущий баланс: {new_karma} ✨")


# --- 3. Выдача Премиума ---
@admin_router.message(Command("add_premium"))
async def cmd_add_premium(message: Message, command: CommandObject, db_pool: asyncpg.Pool, bot: Bot):
    args = command.args.split() if command.args else []
    if len(args) != 2:
        await send_text(bot, message.chat.id, "⚠️ Формат: <code>/add_premium user_id days</code>")
        return

    try:
        target_user_id = int(args[0])
        days = int(args[1])
    except ValueError:
        await send_text(bot, message.chat.id, "⚠️ ID и дни должны быть числами.")
        return

    user_repo = UserRepo(db_pool)
    user = await user_repo.get_user(target_user_id)
    if not user:
        await send_text(bot, message.chat.id, "❌ Пользователь не найден.")
        return

    current_prem = user['premium_date']
    now = datetime.now()

    if current_prem and current_prem > now:
        new_prem_date = current_prem + timedelta(days=days)
    else:
        new_prem_date = now + timedelta(days=days)

    await user_repo.update_user(target_user_id, premium_date=new_prem_date)

    fmt_date = new_prem_date.strftime('%d.%m.%Y')
    await send_text(bot, message.chat.id,
                    f"✅ Подписка выдана пользователю <code>{target_user_id}</code> до <b>{fmt_date}</b>")

    await send_text(
        bot,
        target_user_id,
        f"🎉 <b>Вам выдана Премиум-подписка!</b>\n\n"
        f"Действует до: <b>{fmt_date}</b>"
    )


# --- 4. Управление Ценами ---
@admin_router.message(Command("price"))
async def cmd_set_price(message: Message, command: CommandObject, db_pool: asyncpg.Pool, bot: Bot):
    args = command.args.split() if command.args else []
    if len(args) != 2:
        await send_text(bot, message.chat.id, "⚠️ Формат: <code>/price key value</code>")
        return

    key = args[0]
    value = args[1]

    settings_repo = SettingsRepo(db_pool)
    existing = await settings_repo.get_setting(key)

    if not existing:
        await send_text(bot, message.chat.id, f"⚠️ Настройка <code>{key}</code> не найдена.")
        return

    await settings_repo.update_setting(key, value)

    await send_text(
        bot,
        message.chat.id,
        f"✅ <b>{existing['display_name']}</b> обновлена:\n"
        f"Старое: {existing['value']} -> Новое: <b>{value}</b>"
    )


@admin_router.message(Command("prices"))
async def cmd_show_prices(message: Message, db_pool: asyncpg.Pool, bot: Bot):
    settings_repo = SettingsRepo(db_pool)
    all_settings = await settings_repo.get_all_settings()

    lines = []
    sorted_keys = sorted(all_settings.keys())

    for key in sorted_keys:
        # Показываем только цены и бонусы
        if "price" in key or "bonus" in key:
            data = all_settings[key]
            name = data['display_name']
            val = data['value']
            lines.append(f"🔸 <b>{name}</b>: {val}\n<code>/price {key} {val}</code>")

    text = "💰 <b>Редактор цен и настроек</b>\n\n" + "\n\n".join(lines)
    await send_text(bot, message.chat.id, text)


# ==========================================================
# 📢 РАССЫЛКА (FSM)
# ==========================================================

# 1. Старт: Рассылка ВСЕМ
@admin_router.callback_query(F.data == "admin_mail_all")
async def start_broadcast_all(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await send_text(
        bot,
        callback.message.chat.id,
        "📢 <b>Рассылка ВСЕМ пользователям</b>\n\n"
        "Отправьте сообщение (текст, фото, видео, голосовое), которое вы хотите разослать.\n"
        "Бот пришлет предпросмотр перед отправкой.",
        reply_markup=get_cancel_reply_keyboard()
    )
    await state.update_data(broadcast_type="all")
    await state.set_state(AdminStates.waiting_for_broadcast_msg)
    await callback.answer()


# 1. Старт: Рассылка ОДНОМУ
@admin_router.callback_query(F.data == "admin_mail_one")
async def start_broadcast_one(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await send_text(
        bot,
        callback.message.chat.id,
        "✉️ <b>Введите ID пользователя</b>, которому отправить сообщение:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_for_user_id)
    await callback.answer()


# 2. Обработка ввода ID (для одного)
@admin_router.message(AdminStates.waiting_for_user_id)
async def process_user_id_input(message: Message, state: FSMContext, bot: Bot):
    try:
        target_id = int(message.text)
        await state.update_data(broadcast_type="one", target_id=target_id)

        await send_text(
            bot,
            message.chat.id,
            f"📝 Введите сообщение для пользователя <code>{target_id}</code>:",
            reply_markup=get_cancel_reply_keyboard()
        )
        await state.set_state(AdminStates.waiting_for_broadcast_msg)
    except ValueError:
        await send_text(bot, message.chat.id, "❌ ID должен быть числом.", reply_markup=get_cancel_keyboard())


# 3. Обработка контента и ПРЕДПРОСМОТР
@admin_router.message(AdminStates.waiting_for_broadcast_msg)
async def process_broadcast_content(message: Message, state: FSMContext, bot: Bot):
    # Сохраняем параметры исходного сообщения для метода copy_message
    await state.update_data(
        from_chat_id=message.chat.id,
        message_id=message.message_id
    )

    await send_text(bot, message.chat.id, "👀 <b>Предпросмотр рассылки:</b>")

    try:
        # Копируем сообщение самому себе (админу) для проверки
        await message.copy_to(chat_id=message.chat.id)
    except Exception as e:
        await send_text(bot, message.chat.id, f"❌ Ошибка предпросмотра: {e}")
        return

    await send_text(
        bot,
        message.chat.id,
        "Все верно? Начинаем отправку?",
        reply_markup=get_confirm_broadcast_keyboard()
    )


# 4. Запуск рассылки
@admin_router.callback_query(F.data == "confirm_broadcast")
async def run_broadcast(callback: CallbackQuery, state: FSMContext, db_pool: asyncpg.Pool, bot: Bot):
    data = await state.get_data()
    b_type = data.get("broadcast_type")
    from_chat_id = data.get("from_chat_id")
    message_id = data.get("message_id")

    user_repo = UserRepo(db_pool)

    await edit_text(bot, callback.message.chat.id, callback.message.message_id, "🚀 <b>Рассылка запущена...</b>")

    targets = []
    if b_type == "all":
        targets = await user_repo.get_all_user_ids()
    else:
        targets = [data.get("target_id")]

    success = 0
    fail = 0

    for user_id in targets:
        try:
            # Метод copy_message идеально подходит для рассылок любого контента
            await bot.copy_message(chat_id=user_id, from_chat_id=from_chat_id, message_id=message_id)
            success += 1
        except Exception:
            fail += 1
            # Здесь можно добавить логику пометки пользователя как "blocked", если ошибка Forbidden

    await send_text(
        bot,
        callback.message.chat.id,
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"Успешно: {success}\n"
        f"Ошибок/Блоков: {fail}",
        reply_markup=get_main_menu_keyboard(True)  # Возвращаем главное меню админа
    )
    await state.clear()


# 5. Отмена рассылки
@admin_router.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    await delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await send_text(
        bot,
        callback.message.chat.id,
        "❌ Рассылка отменена.",
        reply_markup=get_main_menu_keyboard(True)
    )
