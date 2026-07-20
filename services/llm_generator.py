import asyncio
from time import perf_counter
from typing import Optional

from loguru import logger
from openai import AsyncOpenAI

from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_FALLBACK_MODELS, OPENROUTER_MODEL
from services.llm_config import LLMSettingsService, PROVIDER_LABELS

LLM_REQUEST_TIMEOUT_SECONDS = 60
LLM_TOTAL_TIMEOUT_SECONDS = 120


class LLMService:
    """Generates responses using the administrator-defined global priority queue."""

    def __init__(self, pool=None):
        self.pool = pool
        self._clients: dict[str, AsyncOpenAI] = {}

    @staticmethod
    def _sanitize_prompt_text(text: str, max_chars: int) -> str:
        return "".join(ch for ch in (text or "") if ch.isprintable() or ch in "\n\t").strip()[:max_chars]

    async def _priority(self) -> list[dict[str, str]]:
        if self.pool:
            return (await LLMSettingsService(self.pool).runtime_config()).priority
        return [
            {"provider": "openrouter", "model": model}
            for model in dict.fromkeys([OPENROUTER_MODEL, *OPENROUTER_FALLBACK_MODELS])
            if model
        ]

    async def _client(self, provider: str) -> AsyncOpenAI:
        if provider in self._clients:
            return self._clients[provider]
        if self.pool:
            settings = LLMSettingsService(self.pool)
            key = settings.provider_key(provider)
            base_url = settings.provider_base_url(provider)
        else:
            key, base_url = OPENROUTER_API_KEY, OPENROUTER_BASE_URL
        if not key:
            raise RuntimeError(f"Не задан API-ключ {PROVIDER_LABELS[provider]}.")
        # SDK retries are disabled deliberately: application-level fallback below is
        # the single source of truth for retry and provider switching.
        client = AsyncOpenAI(
            api_key=key,
            base_url=base_url,
            timeout=LLM_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
        )
        self._clients[provider] = client
        return client

    async def generate_response(
        self,
        user_prompt: str,
        system_prompt: str = "Ты полезный ассистент.",
        max_tokens: int = 1000,
        temperature: float = 0.7,
        total_timeout_seconds: int = LLM_TOTAL_TIMEOUT_SECONDS,
    ) -> Optional[str]:
        system = self._sanitize_prompt_text(system_prompt, 6000)
        user = self._sanitize_prompt_text(user_prompt, 12000)
        if not user:
            logger.warning("Пустой LLM-промпт после санитизации.")
            return None

        priority = await self._priority()
        if not priority:
            logger.error("Очередь LLM-моделей пуста.")
            return None

        started_at = perf_counter()
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for item in priority:
            elapsed_seconds = perf_counter() - started_at
            if elapsed_seconds >= total_timeout_seconds:
                logger.warning(
                    f"Превышен общий лимит ожидания LLM: {total_timeout_seconds} сек."
                )
                break
            provider, model = item["provider"], item["model"]
            try:
                client = await self._client(provider)
            except Exception as exc:
                logger.error(f"LLM-провайдер {PROVIDER_LABELS[provider]} недоступен: {exc}")
                continue

            remaining_seconds = total_timeout_seconds - (perf_counter() - started_at)
            if remaining_seconds <= 0:
                break
            try:
                request_timeout = min(LLM_REQUEST_TIMEOUT_SECONDS, remaining_seconds)
                logger.info(
                    f"🎯 LLM: {PROVIDER_LABELS[provider]} / {model}, "
                    f"тайм-аут={int(request_timeout)} сек."
                )
                async with asyncio.timeout(request_timeout):
                    response = await client.chat.completions.create(
                        model=model, messages=messages, max_tokens=max_tokens,
                        temperature=temperature, top_p=0.95,
                    )
                answer = (response.choices[0].message.content or "").strip()
                if not answer:
                    raise RuntimeError("Провайдер вернул пустой ответ.")
                logger.success(
                    f"✅ Ответ LLM: {PROVIDER_LABELS[provider]} / {model}, "
                    f"elapsed_ms={int((perf_counter() - started_at) * 1000)}"
                )
                return answer
            except Exception as exc:
                logger.warning(
                    f"Ошибка {PROVIDER_LABELS[provider]} / {model}: {exc}. Переходим к следующей позиции приоритета."
                )

        logger.error(f"❌ Все LLM-варианты исчерпаны за {int((perf_counter() - started_at) * 1000)} мс.")
        return None
