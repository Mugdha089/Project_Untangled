from __future__ import annotations

import unittest
from unittest.mock import patch
import os

import httpx

from ai_providers import (
    AIProviderConfigurationError,
    AIProviderUnavailableError,
    AIProvidersDisabledError,
    ProviderConfig,
    generate_gemini,
    generate_huggingface,
    generate_xai,
    load_provider_config,
)


class AIProviderAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.config = ProviderConfig(
            enabled=True,
            gemini_api_key="test-gemini-key",
            xai_api_key="test-xai-key",
            hf_token="test-hf-token",
            gemini_model="gemini-test-model",
            xai_model="grok-4.7",
            hf_model="org/test-model",
        )

    def test_backend_environment_configuration_defaults_to_disabled(self) -> None:
        with patch.dict(os.environ, {
            "AI_PROVIDERS_ENABLED": "false", "GEMINI_API_KEY": "", "XAI_API_KEY": "", "HF_TOKEN": "",
            "XAI_MODEL": "grok-4.7",
        }):
            config = load_provider_config()
        self.assertFalse(config.enabled)
        self.assertEqual(config.gemini_api_key, "")
        self.assertEqual(config.xai_api_key, "")
        self.assertEqual(config.hf_token, "")
        self.assertEqual(config.xai_model, "grok-4.7")

    async def test_disabled_providers_make_no_request(self) -> None:
        async def unexpected(_: httpx.Request) -> httpx.Response:
            self.fail("disabled provider must not make a network request")

        with self.assertRaises(AIProvidersDisabledError):
            await generate_gemini(
                "test", config=ProviderConfig(), transport=httpx.MockTransport(unexpected)
            )

    async def test_missing_credentials_are_reported_without_network_access(self) -> None:
        with self.assertRaisesRegex(AIProviderConfigurationError, "GEMINI_API_KEY"):
            await generate_gemini(
                "test", config=ProviderConfig(enabled=True),
                transport=httpx.MockTransport(lambda _: self.fail("unexpected request")),
            )

    async def test_gemini_uses_backend_key_header_and_documented_request_shape(self) -> None:
        async def respond(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.host, "generativelanguage.googleapis.com")
            self.assertEqual(request.headers["x-goog-api-key"], "test-gemini-key")
            self.assertEqual(request.url.path, "/v1beta/models/gemini-test-model:generateContent")
            self.assertEqual(await request.aread(), b'{"contents":[{"parts":[{"text":"read this"}]}]}')
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "review only"}]}}]})

        result = await generate_gemini(
            "read this", config=self.config, transport=httpx.MockTransport(respond)
        )
        self.assertEqual(result, "review only")

    async def test_xai_uses_responses_api_and_bearer_key(self) -> None:
        async def respond(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url, "https://api.x.ai/v1/responses")
            self.assertEqual(request.headers["Authorization"], "Bearer test-xai-key")
            self.assertEqual(request.headers["Content-Type"], "application/json")
            self.assertEqual(await request.aread(), b'{"model":"grok-4.7","input":"check this"}')
            return httpx.Response(200, json={"output": [{"type": "message", "content": [{"type": "output_text", "text": "unverified suggestion"}]}]})

        result = await generate_xai(
            "check this", config=self.config, transport=httpx.MockTransport(respond)
        )
        self.assertEqual(result, "unverified suggestion")

    async def test_huggingface_uses_inference_router_and_bearer_token(self) -> None:
        async def respond(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url, "https://router.huggingface.co/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer test-hf-token")
            return httpx.Response(200, json={"choices": [{"message": {"content": "advisory"}}]})

        result = await generate_huggingface(
            "check this", config=self.config, transport=httpx.MockTransport(respond)
        )
        self.assertEqual(result, "advisory")

    async def test_auth_rate_limit_and_unavailable_model_errors_are_sanitized(self) -> None:
        for status, expected in (
            (400, AIProviderConfigurationError),
            (401, AIProviderConfigurationError),
            (429, AIProviderUnavailableError),
            (404, AIProviderConfigurationError),
            (503, AIProviderUnavailableError),
        ):
            async def respond(_: httpx.Request, code: int = status) -> httpx.Response:
                return httpx.Response(code, text="provider error includes test-xai-key")

            with self.subTest(status=status):
                with self.assertRaises(expected) as error:
                    await generate_xai(
                        "test", config=self.config, transport=httpx.MockTransport(respond)
                    )
                self.assertNotIn("test-xai-key", str(error.exception))

    async def test_timeout_is_reported(self) -> None:
        async def timeout(_: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("test timeout")

        with self.assertRaisesRegex(AIProviderUnavailableError, "timed out"):
            await generate_huggingface(
                "test", config=self.config, transport=httpx.MockTransport(timeout)
            )


if __name__ == "__main__":
    unittest.main()
