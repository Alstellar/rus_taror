import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# --- bootstrap optional dependency: dotenv ---
if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")

    def _load_dotenv(*args, **kwargs):
        return True

    dotenv_stub.load_dotenv = _load_dotenv
    sys.modules["dotenv"] = dotenv_stub

# --- bootstrap optional dependency: openai ---
if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class _DummyAPIError(Exception):
        pass

    class _DummyRateLimitError(Exception):
        pass

    class _DummyAsyncOpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=None))

    openai_stub.AsyncOpenAI = _DummyAsyncOpenAI
    openai_stub.APIError = _DummyAPIError
    openai_stub.RateLimitError = _DummyRateLimitError
    sys.modules["openai"] = openai_stub

# --- bootstrap optional dependency: loguru ---
if "loguru" not in sys.modules:
    loguru_stub = types.ModuleType("loguru")

    class _DummyLogger:
        def __getattr__(self, name):
            def _noop(*args, **kwargs):
                return None
            return _noop

    loguru_stub.logger = _DummyLogger()
    sys.modules["loguru"] = loguru_stub

import services.llm_generator as llm_module


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


class LLMServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_none_without_api_key(self):
        with patch.object(llm_module, "OPENROUTER_API_KEY", None), \
             patch.object(llm_module, "OPENROUTER_MODEL", "primary/model"), \
             patch.object(llm_module, "OPENROUTER_FALLBACK_MODELS", ["fallback/model"]):
            svc = llm_module.LLMService()
            result = await svc.generate_response("hello", "system")
            self.assertIsNone(result)

    async def test_switches_to_fallback_model_when_primary_unavailable(self):
        calls = []

        class FakeCompletions:
            async def create(self, *, model, messages, max_tokens, temperature, top_p):
                calls.append(model)
                if model == "primary/model":
                    raise Exception("model not found")
                return _FakeResponse("ok from fallback")

        class FakeClient:
            def __init__(self):
                self.chat = SimpleNamespace(completions=FakeCompletions())

        class FakeAsyncOpenAI:
            def __init__(self, api_key, base_url):
                self._api_key = api_key
                self._base_url = base_url
                self.chat = FakeClient().chat

        with patch.object(llm_module, "OPENROUTER_API_KEY", "test-key"), \
             patch.object(llm_module, "OPENROUTER_MODEL", "primary/model"), \
             patch.object(llm_module, "OPENROUTER_FALLBACK_MODELS", ["fallback/model"]), \
             patch.object(llm_module, "AsyncOpenAI", FakeAsyncOpenAI), \
             patch.object(llm_module, "APIError", Exception):
            svc = llm_module.LLMService()
            result = await svc.generate_response("hello", "system", retries=1)

        self.assertEqual(result, "ok from fallback")
        self.assertEqual(calls, ["primary/model", "fallback/model"])

    async def test_returns_none_when_all_models_fail(self):
        class FakeCompletions:
            async def create(self, *, model, messages, max_tokens, temperature, top_p):
                raise Exception("provider unavailable")

        class FakeClient:
            def __init__(self):
                self.chat = SimpleNamespace(completions=FakeCompletions())

        class FakeAsyncOpenAI:
            def __init__(self, api_key, base_url):
                self.chat = FakeClient().chat

        with patch.object(llm_module, "OPENROUTER_API_KEY", "test-key"), \
             patch.object(llm_module, "OPENROUTER_MODEL", "primary/model"), \
             patch.object(llm_module, "OPENROUTER_FALLBACK_MODELS", ["fallback/model"]), \
             patch.object(llm_module, "AsyncOpenAI", FakeAsyncOpenAI), \
             patch.object(llm_module, "APIError", Exception):
            svc = llm_module.LLMService()
            result = await svc.generate_response("hello", "system", retries=1)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
