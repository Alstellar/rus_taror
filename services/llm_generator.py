import asyncio
from typing import Optional
from openai import AsyncOpenAI, APIError, RateLimitError
from loguru import logger
from config import SAMBANOVA_API_KEY, SAMBANOVA_MODEL


class LLMService:
    def __init__(self):
        if not SAMBANOVA_API_KEY:
            logger.critical("⚠️ SAMBANOVA_API_KEY не найден в конфигурации! LLM не будет работать.")
            self.client = None
        else:
            # Инициализация клиента.
            # SambaNova использует API, совместимый с OpenAI.
            self.client = AsyncOpenAI(
                api_key=SAMBANOVA_API_KEY,
                base_url="https://api.sambanova.ai/v1",
            )

    async def generate_response(
            self,
            user_prompt: str,
            system_prompt: str = "Ты полезный ассистент.",
            max_tokens: int = 1000,
            temperature: float = 0.7,
            retries: int = 3
    ) -> Optional[str]:
        """
        Генерирует ответ от LLM (SambaNova) с механизмом повторных попыток.

        :param user_prompt: Основной запрос пользователя.
        :param system_prompt: Инструкция для нейросети (роль, формат ответа).
        :param max_tokens: Лимит токенов на выход.
        :param temperature: Степень креативности (0.0 - строгий, 1.0 - случайный).
        :param retries: Количество попыток при ошибке.
        :return: Текст ответа или None в случае неудачи.
        """
        if not self.client:
            logger.error("Попытка использовать LLM без инициализированного клиента.")
            return "Извините, сервис искусственного интеллекта временно недоступен (ошибка конфигурации)."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        for attempt in range(1, retries + 1):
            try:
                logger.info(f"⏳ Запрос к LLM (попытка {attempt}/{retries})...")

                response = await self.client.chat.completions.create(
                    model=SAMBANOVA_MODEL,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=0.95  # Стандартное значение для Llama
                )

                answer = response.choices[0].message.content.strip()

                # Простая проверка на пустой ответ
                if not answer:
                    logger.warning("LLM вернула пустой ответ.")
                    continue

                logger.success("✅ Ответ от LLM получен успешно.")
                return answer

            except RateLimitError:
                logger.warning(f"⚠️ Превышен лимит запросов (Rate Limit). Ждем перед повтором...")
                await asyncio.sleep(2 * attempt)  # Экспоненциальная задержка
            except APIError as e:
                logger.error(f"❌ Ошибка API SambaNova: {e}")
                await asyncio.sleep(1)
            except Exception as e:
                logger.exception(f"❌ Непредвиденная ошибка при запросе к LLM: {e}")
                await asyncio.sleep(1)

        logger.error("❌ Не удалось получить ответ от LLM после всех попыток.")
        return "К сожалению, магический шар сейчас затуманен. Попробуйте повторить запрос чуть позже."