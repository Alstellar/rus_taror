# services/media_loader.py
import os
import asyncpg
from loguru import logger
from db import ImageRepo
from utils.card_mapping import CARD_NAME_MAPPING, BOT_IMAGE_MAPPING

ASSETS_DIR = "assets"


class MediaLoaderService:
    def __init__(self, pool: asyncpg.Pool):
        self.repo = ImageRepo(pool)

    async def scan_and_load_folder(self, folder_name: str):
        """
        Сканирует указанную папку в /assets/ и обновляет БД.
        """
        full_path = os.path.join(os.getcwd(), ASSETS_DIR, folder_name)

        if not os.path.exists(full_path):
            logger.error(f"❌ Папка не найдена: {full_path}")
            return

        logger.info(f"📂 Начало сканирования папки: {folder_name} ...")

        files = os.listdir(full_path)
        processed_count = 0
        skipped_count = 0

        # Определяем логику маппинга
        is_gif_folder = folder_name.startswith("gifs_")  # gifts_tarot, gifts_astro...
        mapping = {}
        is_tarot = False

        if not is_gif_folder:
            if folder_name == "bot_images":
                mapping = BOT_IMAGE_MAPPING
                is_tarot = False
            else:
                mapping = CARD_NAME_MAPPING
                is_tarot = True

        for filename in files:
            # Поддерживаем и картинки, и гифки
            if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.mp4')):
                continue

            en_name = os.path.splitext(filename)[0]

            # Логика определения данных
            if is_gif_folder:
                # Для гифок берем дефолтные значения, маппинг не нужен
                ru_name = "Анимация ожидания"
                arcana = None
            else:
                # Для карт и системных картинок ищем в маппинге
                item_data = mapping.get(en_name)
                if not item_data:
                    logger.warning(f"⚠️ Файл '{filename}' игнорируется (нет в mapping)")
                    skipped_count += 1
                    continue

                if is_tarot:
                    ru_name = item_data.get("ru", "Неизвестно")
                    arcana = item_data.get("arcana")
                else:
                    ru_name = item_data
                    arcana = None

            relative_path = os.path.join(ASSETS_DIR, folder_name, filename)

            await self.repo.insert_or_update_image(
                dict_name=folder_name,
                en=en_name,
                ru=ru_name,
                arcana=arcana,
                image_path=relative_path
            )
            processed_count += 1

        logger.success(f"✅ Сканирование '{folder_name}' завершено. Загружено: {processed_count}")