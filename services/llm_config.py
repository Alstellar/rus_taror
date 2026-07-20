import json
from dataclasses import dataclass
from typing import Any


from config import (
    CLAUDEHUB_API_KEY,
    CLAUDEHUB_BASE_URL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_FALLBACK_MODELS,
    OPENROUTER_MODEL,
)
from db import SettingsRepo

PROVIDERS = ("openrouter", "claudehub")
PROVIDER_LABELS = {"openrouter": "OpenRouter", "claudehub": "ClaudeHub"}
PRIORITY_SLOTS = 10


def default_openrouter_models() -> list[str]:
    return list(dict.fromkeys([OPENROUTER_MODEL, *OPENROUTER_FALLBACK_MODELS]))


def default_priority() -> list[dict[str, str] | None]:
    models = default_openrouter_models()
    return [{"provider": "openrouter", "model": model} for model in models[:PRIORITY_SLOTS]] + [None] * max(0, PRIORITY_SLOTS - len(models))


def _decode_models(raw: str | None, fallback: list[str]) -> list[str]:
    try:
        value = json.loads(raw or "")
        if isinstance(value, list):
            return list(dict.fromkeys(item.strip() for item in value if isinstance(item, str) and item.strip()))
    except json.JSONDecodeError:
        pass
    return fallback


def _decode_priority(raw: str | None) -> list[dict[str, str] | None]:
    result: list[dict[str, str] | None] = []
    try:
        value = json.loads(raw or "")
        if isinstance(value, list):
            for item in value[:PRIORITY_SLOTS]:
                if isinstance(item, dict) and item.get("provider") in PROVIDERS and isinstance(item.get("model"), str) and item["model"].strip():
                    result.append({"provider": item["provider"], "model": item["model"].strip()})
                else:
                    result.append(None)
    except json.JSONDecodeError:
        pass
    return result + [None] * (PRIORITY_SLOTS - len(result))


@dataclass(frozen=True)
class LLMRuntimeConfig:
    priority: list[dict[str, str]]


class LLMSettingsService:
    def __init__(self, pool):
        self.repo = SettingsRepo(pool)

    async def get_openrouter_models(self) -> list[str]:
        setting = await self.repo.get_setting("llm_openrouter_models")
        return _decode_models(setting["value"] if setting else None, default_openrouter_models())

    async def save_openrouter_models(self, models: list[str]) -> None:
        cleaned = list(dict.fromkeys(model.strip() for model in models if model.strip()))
        await self.repo.update_setting("llm_openrouter_models", json.dumps(cleaned), "Модели OpenRouter")

    async def get_priority(self) -> list[dict[str, str] | None]:
        setting = await self.repo.get_setting("llm_priority")
        return _decode_priority(setting["value"] if setting else None)

    async def save_priority(self, priority: list[dict[str, str] | None]) -> None:
        await self.repo.update_setting("llm_priority", json.dumps(priority), "Приоритет LLM")

    async def runtime_config(self) -> LLMRuntimeConfig:
        priority = [item for item in await self.get_priority() if item]
        return LLMRuntimeConfig(priority=priority or [item for item in default_priority() if item])

    @staticmethod
    def provider_key(provider: str) -> str:
        return OPENROUTER_API_KEY if provider == "openrouter" else CLAUDEHUB_API_KEY

    @staticmethod
    def provider_base_url(provider: str) -> str:
        return OPENROUTER_BASE_URL if provider == "openrouter" else CLAUDEHUB_BASE_URL

    async def claudehub_models(self) -> list[str]:
        import httpx
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{CLAUDEHUB_BASE_URL.rstrip('/')}/models")
            response.raise_for_status()
        data = response.json().get("data", [])
        return sorted({item.get("id", "").strip() for item in data if isinstance(item, dict) and item.get("id")})

    async def balance(self, provider: str) -> tuple[float, str]:
        import httpx
        key = self.provider_key(provider)
        if not key:
            raise RuntimeError(f"Не задан API-ключ {PROVIDER_LABELS[provider]}.")
        headers = {"Authorization": f"Bearer {key}"}
        async with httpx.AsyncClient(timeout=20) as client:
            if provider == "openrouter":
                response = await client.get(f"{OPENROUTER_BASE_URL.rstrip('/')}/credits", headers=headers)
                response.raise_for_status()
                data = response.json().get("data", {})
                return max(0, float(data.get("total_credits", 0)) - float(data.get("total_usage", 0))), "USD"
            response = await client.get(f"{CLAUDEHUB_BASE_URL.rstrip('/')}/balance", headers=headers)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return float(data.get("balance", 0)), str(data.get("currency", "USD"))
