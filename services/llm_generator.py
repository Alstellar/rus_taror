import asyncio
from time import perf_counter
from typing import Optional
from openai import AsyncOpenAI, APIError, RateLimitError
from loguru import logger
from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
    OPENROUTER_FALLBACK_MODELS,
)


class LLMService:
    def __init__(self):
        if not OPENROUTER_API_KEY:
            logger.critical("⚠️ OPENROUTER_API_KEY не найден в конфигурации! LLM не будет работать.")
            self.client = None
            self.models = []
        else:
            # OpenRouter предоставляет OpenAI-совместимый API.
            self.client = AsyncOpenAI(
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
            )
            self.models = self._build_model_chain()

    @staticmethod
    def _build_model_chain() -> list[str]:
        """Формирует цепочку моделей: основная + fallback без дублей."""
        seen = set()
        chain = []

        for model in [OPENROUTER_MODEL, *OPENROUTER_FALLBACK_MODELS]:
            if model and model not in seen:
                seen.add(model)
                chain.append(model)

        return chain

    @staticmethod
    def _sanitize_prompt_text(text: str, max_chars: int) -> str:
        """Санитизирует текст промпта: убирает управляющие символы и ограничивает длину."""
        if not text:
            return ""
        cleaned = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t")
        return cleaned.strip()[:max_chars]

    @staticmethod
    def _is_model_unavailable_error(error: APIError) -> bool:
        """
        Определяет, что модель недоступна (не найдена, нет доступного провайдера и т.д.).
        В таком случае имеет смысл сразу переключиться на fallback-модель.
        """
        msg = str(error).lower()
        unavailable_markers = (
            "model not found",
            "unknown model",
            "no endpoints found",
            "no endpoints",
            "provider unavailable",
            "not available",
            "unavailable",
        )
        return any(marker in msg for marker in unavailable_markers)

    async def generate_response(
            self,
            user_prompt: str,
            system_prompt: str = "Ты полезный ассистент.",
            max_tokens: int = 1000,
            temperature: float = 0.7,
            retries: int = 3
    ) -> Optional[str]:
        """
        Генерирует ответ от LLM (OpenRouter) с механизмом повторных попыток.

        :param user_prompt: Основной запрос пользователя.
        :param system_prompt: Инструкция для нейросети (роль, формат ответа).
        :param max_tokens: Лимит токенов на выход.
        :param temperature: Степень креативности (0.0 - строгий, 1.0 - случайный).
        :param retries: Количество попыток при ошибке.
        :return: Текст ответа или None в случае неудачи.
        """
        if not self.client:
            logger.error("Попытка использовать LLM без инициализированного клиента.")
            return None

        if not self.models:
            logger.error("Список моделей OpenRouter пуст. Проверьте OPENROUTER_MODEL / OPENROUTER_FALLBACK_MODELS.")
            return None

        prepared_system_prompt = self._sanitize_prompt_text(system_prompt, 6000)
        prepared_user_prompt = self._sanitize_prompt_text(user_prompt, 12000)
        if not prepared_user_prompt:
            logger.warning("Пустой пользовательский промпт после санитизации.")
            return None

        messages = [
            {"role": "system", "content": prepared_system_prompt},
            {"role": "user", "content": prepared_user_prompt}
        ]

        started_at = perf_counter()
        total_attempts = 0
        for model in self.models:
            logger.info(f"🎯 Текущая модель LLM: {model}")

            for attempt in range(1, retries + 1):
                total_attempts += 1
                try:
                    logger.info(f"⏳ Запрос к LLM (модель={model}, попытка {attempt}/{retries})...")

                    response = await self.client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=0.95  # Стандартное значение для Llama
                    )

                    answer = response.choices[0].message.content.strip()

                    # Простая проверка на пустой ответ
                    if not answer:
                        logger.warning(f"LLM вернула пустой ответ (модель={model}).")
                        continue

                    elapsed_ms = int((perf_counter() - started_at) * 1000)
                    logger.success(
                        f"✅ Ответ от LLM получен успешно (model={model}, attempts={total_attempts}, elapsed_ms={elapsed_ms}, "
                        f"prompt_chars={len(prepared_user_prompt)}, answer_chars={len(answer)})."
                    )
                    return answer

                except RateLimitError:
                    logger.warning("⚠️ Превышен лимит запросов (Rate Limit). Ждем перед повтором...")
                    await asyncio.sleep(2 * attempt)  # Экспоненциальная задержка
                except APIError as e:
                    if self._is_model_unavailable_error(e):
                        logger.warning(f"⚠️ Модель недоступна ({model}): {e}. Переключаемся на fallback.")
                        break

                    logger.error(f"❌ Ошибка API OpenRouter (модель={model}): {e}")
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.exception(f"❌ Непредвиденная ошибка при запросе к LLM (модель={model}): {e}")
                    await asyncio.sleep(1)

        elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.error(
            f"❌ Не удалось получить ответ от LLM после всех попыток "
            f"(attempts={total_attempts}, elapsed_ms={elapsed_ms}, prompt_chars={len(prepared_user_prompt)})."
        )
        return None
