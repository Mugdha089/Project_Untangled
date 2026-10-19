from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import httpx

import ai_providers
import provider_diagnostic
from ai_providers import ProviderConfig, _key_shape, _load_backend_dotenv
from provider_diagnostic import (
    check_provider,
    check_xai_model_availability,
    format_diagnostic_result,
)


class ProviderDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_reports_status_without_retaining_provider_text(self) -> None:
        async def respond(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "secret response text"}]}}]})

        result = await check_provider(
            "gemini",
            config=ProviderConfig(enabled=True, gemini_api_key="mock-key"),
            transport=httpx.MockTransport(respond),
        )
        self.assertEqual((result.success, result.category, result.status_code), (True, "ok", 200))
        self.assertNotIn("secret response text", repr(result))
        self.assertNotIn("mock-key", repr(result))

    async def test_failure_reports_sanitized_category_and_http_status(self) -> None:
        async def respond(_: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {
                "code": "invalid_api_key",
                "message": "invalid key mock-key and Bearer mock-key",
            }})

        result = await check_provider(
            "xai",
            config=ProviderConfig(enabled=True, xai_api_key="mock-key"),
            transport=httpx.MockTransport(respond),
        )
        self.assertEqual((result.success, result.category, result.status_code),
                         (False, "authentication", 401))
        self.assertNotIn("mock-key", repr(result))
        output = StringIO()
        with redirect_stdout(output):
            print(format_diagnostic_result(result))
        self.assertNotIn("mock-key", output.getvalue())

    async def test_http_status_categories_are_distinct(self) -> None:
        expected_categories = {
            400: "request_rejected",
            401: "authentication",
            403: "permission_denied",
            404: "model_or_endpoint_not_found",
            422: "request_validation",
            429: "rate_limited",
        }
        for status, expected in expected_categories.items():
            async def respond(_: httpx.Request, code: int = status) -> httpx.Response:
                return httpx.Response(code, json={"error": {"code": "unrecognized", "message": "safe"}})

            result = await check_provider(
                "xai",
                config=ProviderConfig(enabled=True, xai_api_key="mock-key", xai_model="grok-4.7"),
                transport=httpx.MockTransport(respond),
            )
            self.assertEqual(result.category, expected, f"status {status}")

        async def model_missing(_: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": {"code": "model_not_found", "message": "private detail"}})

        model_result = await check_provider(
            "xai",
            config=ProviderConfig(enabled=True, xai_api_key="mock-key", xai_model="grok-4.7"),
            transport=httpx.MockTransport(model_missing),
        )
        self.assertEqual(model_result.category, "model_unavailable")
        self.assertNotIn("private detail", repr(model_result))

    async def test_http_400_is_reported_as_request_rejected_not_invalid_configuration(self) -> None:
        async def respond(_: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={
                "error": {
                    "code": "invalid_argument",
                    "message": "Bad input; rejected prompt 'Reply with the single word OK.' and mock-key",
                }
            })

        result = await check_provider(
            "xai",
            config=ProviderConfig(enabled=True, xai_api_key="mock-key", xai_model="grok-4.7"),
            transport=httpx.MockTransport(respond),
        )
        self.assertEqual((result.success, result.category, result.status_code),
                         (False, "request_validation", 400))
        self.assertEqual(result.provider_code, "invalid_argument")
        self.assertEqual(result.provider_message, "Request validation failed.")
        self.assertNotIn("Bad input", repr(result))
        self.assertNotIn("Reply with the single word OK.", repr(result))
        self.assertNotIn("mock-key", repr(result))

    async def test_xai_400_diagnostics_expose_only_allowlisted_metadata(self) -> None:
        prompt = "Reply with the single word OK."
        mock_key = "mock-key"
        fake_token = "xai-ABCDEFGHIJKLMNOPQRSTUVWX"
        private_id = "private-team-42"
        bodies = (
            ("string-error", b'{"error":"api key model permission ' + mock_key.encode() + b" " + fake_token.encode() + b" " + private_id.encode() + b'"}', "application/json", ("error",), "str"),
            ("dict-error", b'{"error":{"code":"invalid_argument","message":"api key model permission ' + prompt.encode() + b" " + mock_key.encode() + b" " + private_id.encode() + b'"},"private-team-42":"hidden"}', "application/json", ("error", "other"), "dict"),
            ("plain-text", ("api key model permission " + mock_key + " " + fake_token + " " + private_id).encode(), "text/plain", None, None),
            ("empty", b"", "application/json", None, None),
        )

        for case, body, content_type, json_keys, error_type in bodies:
            with self.subTest(case=case):
                async def respond(request: httpx.Request) -> httpx.Response:
                    self.assertEqual(request.method, "POST")
                    self.assertEqual(request.url, "https://api.x.ai/v1/responses")
                    self.assertEqual(request.headers["Authorization"], f"Bearer {mock_key}")
                    self.assertEqual(await request.aread(), b'{"model":"grok-4.7","input":"Reply with the single word OK."}')
                    return httpx.Response(400, content=body, headers={"content-type": content_type})

                result = await check_provider(
                    "xai",
                    config=ProviderConfig(enabled=True, xai_api_key=mock_key, xai_model="grok-4.7"),
                    transport=httpx.MockTransport(respond),
                )
                self.assertEqual(result.xai_request, "responses")
                self.assertEqual(result.response_content_type, content_type)
                self.assertEqual(result.body_length_bytes, len(body))
                self.assertEqual(result.top_level_json_keys, json_keys)
                self.assertEqual(result.error_value_type, error_type)
                if case == "empty":
                    self.assertEqual(result.category, "request_rejected")
                if case == "string-error":
                    self.assertEqual(result.category, "credential_rejected")
                    self.assertEqual(result.provider_message, "Provider rejected the request.")
                if case == "empty":
                    self.assertEqual((result.mentions_api_key, result.mentions_model, result.mentions_permission), (False, False, False))
                else:
                    self.assertEqual((result.mentions_api_key, result.mentions_model, result.mentions_permission), (True, True, True))
                output = format_diagnostic_result(result)
                self.assertNotIn("\n", output)
                for sensitive in (mock_key, fake_token, private_id, prompt):
                    self.assertNotIn(sensitive, repr(result))
                    self.assertNotIn(sensitive, output)

    async def test_xai_key_source_and_shape_are_reported_without_values(self) -> None:
        with patch.dict(os.environ, {"PYTHON_DOTENV_DISABLED": "", "XAI_API_KEY": "mock-process-value"}):
            source = _load_backend_dotenv(Path("missing-test-file.env"))
            self.assertEqual(source, "process_env")
            shape = _key_shape(os.environ["XAI_API_KEY"])
            with patch.object(provider_diagnostic, "XAI_API_KEY_SOURCE", source), patch.object(
                ai_providers, "_XAI_KEY_SHAPE", shape
            ):
                process_result = await self._run_xai_metadata_check("mock-key")
            self.assertEqual(process_result.xai_key_source, "process_env")

        self.assertEqual(process_result.xai_key_length, len("mock-process-value"))
        self.assertFalse(process_result.xai_key_starts_with_prefix)

        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / "test-only.env"
            dotenv_path.write_text("XAI_API_KEY=mock-dotenv-value\n", encoding="utf-8")
            with patch.dict(os.environ, {"PYTHON_DOTENV_DISABLED": ""}):
                os.environ.pop("XAI_API_KEY", None)
                source = _load_backend_dotenv(dotenv_path)
                self.assertEqual(source, "dotenv_file")
                shape = _key_shape(os.environ["XAI_API_KEY"])
                with patch.object(provider_diagnostic, "XAI_API_KEY_SOURCE", source), patch.object(
                    ai_providers, "_XAI_KEY_SHAPE", shape
                ):
                    dotenv_result = await self._run_xai_metadata_check("mock-key")
            self.assertEqual(dotenv_result.xai_key_source, "dotenv_file")
            self.assertEqual(dotenv_result.xai_key_length, len("mock-dotenv-value"))

        for result in (process_result, dotenv_result):
            output = format_diagnostic_result(result)
            self.assertNotIn("mock-process-value", repr(result) + output)
            self.assertNotIn("mock-dotenv-value", repr(result) + output)

    async def test_xai_key_fingerprint_reports_only_requested_shape(self) -> None:
        test_key = " xai-test-α ' "
        shape = _key_shape(test_key)
        with patch.object(ai_providers, "_XAI_KEY_SHAPE", shape), patch.object(
            provider_diagnostic, "XAI_API_KEY_SOURCE", "process_env"
        ):
            result = await self._run_xai_metadata_check(test_key)

        self.assertEqual(result.xai_key_length, len(test_key.strip()))
        self.assertTrue(result.xai_key_starts_with_prefix)
        self.assertTrue(result.xai_key_has_outer_whitespace)
        self.assertTrue(result.xai_key_contains_non_ascii)
        self.assertTrue(result.xai_key_contains_quotes)
        self.assertTrue(result.xai_key_contains_inner_whitespace)
        self.assertNotIn(test_key, repr(result))

    async def _run_xai_metadata_check(self, credential: str):
        async def respond(_: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "api key"})

        return await check_provider(
            "xai",
            config=ProviderConfig(enabled=True, xai_api_key=credential, xai_model="grok-4.7"),
            transport=httpx.MockTransport(respond),
        )

    async def test_output_redacts_configured_key_prompt_and_common_secret_formats(self) -> None:
        credential = "mock-key"
        prompt = "Reply with the single word OK."
        common_token = "xai-ABCDEFGHIJKLMNOPQRSTUVWX"
        private_identifiers = ("private-team", "secret-project-78", "account-prod-42", "resource-991")

        async def respond(_: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {
                "code": "invalid_argument",
                "message": (
                    f"{prompt}; credential={credential}; token={common_token}; Bearer {credential}; "
                    + "; ".join(private_identifiers)
                ),
            }})

        result = await check_provider(
            "xai",
            config=ProviderConfig(enabled=True, xai_api_key=credential, xai_model="grok-4.7"),
            transport=httpx.MockTransport(respond),
        )
        output = StringIO()
        with redirect_stdout(output):
            print(format_diagnostic_result(result))
        for text in (credential, prompt, common_token, *private_identifiers):
            self.assertNotIn(text, repr(result))
            self.assertNotIn(text, output.getvalue())

    async def test_malformed_or_unallowlisted_error_is_generic(self) -> None:
        async def malformed(_: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="mock-key raw body private-team prompt-secret arbitrary-token")

        malformed_result = await check_provider(
            "xai",
            config=ProviderConfig(enabled=True, xai_api_key="mock-key", xai_model="grok-4.7"),
            transport=httpx.MockTransport(malformed),
        )
        self.assertEqual((malformed_result.category, malformed_result.provider_code,
                          malformed_result.provider_message),
                         ("request_rejected", None, "Provider rejected the request."))
        malformed_output = StringIO()
        with redirect_stdout(malformed_output):
            print(format_diagnostic_result(malformed_result))
        for secret in ("mock-key", "raw body", "private-team", "prompt-secret", "arbitrary-token"):
            self.assertNotIn(secret, repr(malformed_result))
            self.assertNotIn(secret, malformed_output.getvalue())

        async def unexpected_shape(_: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "mock-key must not be reported"})

        shape_result = await check_provider(
            "xai",
            config=ProviderConfig(enabled=True, xai_api_key="mock-key", xai_model="grok-4.7"),
            transport=httpx.MockTransport(unexpected_shape),
        )
        self.assertEqual((shape_result.category, shape_result.provider_code,
                          shape_result.provider_message),
                         ("request_rejected", None, "Provider rejected the request."))
        self.assertNotIn("mock-key", repr(shape_result))
        self.assertNotIn("mock-key must not be reported", format_diagnostic_result(shape_result))

    async def test_model_list_check_reports_only_configured_model_match(self) -> None:
        async def respond(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url, "https://api.x.ai/v1/models")
            self.assertEqual(request.headers["Authorization"], "Bearer mock-key")
            return httpx.Response(200, json={"data": [
                {"id": "another-model", "aliases": []},
                {"id": "canonical-name", "aliases": ["grok-4.7"]},
            ]})

        result = await check_xai_model_availability(
            config=ProviderConfig(enabled=True, xai_api_key="mock-key", xai_model="grok-4.7"),
            transport=httpx.MockTransport(respond),
        )
        self.assertEqual((result.success, result.category, result.model_available,
                          result.status_code), (True, "model_available", True, 200))
        self.assertNotIn("another-model", repr(result))
        self.assertNotIn("mock-key", repr(result))

    async def test_model_list_check_reports_absent_model_without_listing_models(self) -> None:
        async def respond(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"id": "other", "aliases": []}]})

        result = await check_xai_model_availability(
            config=ProviderConfig(enabled=True, xai_api_key="mock-key", xai_model="grok-4.7"),
            transport=httpx.MockTransport(respond),
        )
        self.assertEqual((result.success, result.category, result.model_available),
                         (True, "model_not_listed", False))
        self.assertNotIn("other", repr(result))

    async def test_model_list_check_handles_malformed_json_without_details(self) -> None:
        async def respond(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not-json; xai-ABCDEFGHIJKLMNOPQRSTUVWX")

        result = await check_xai_model_availability(
            config=ProviderConfig(enabled=True, xai_api_key="mock-key", xai_model="grok-4.7"),
            transport=httpx.MockTransport(respond),
        )
        self.assertEqual((result.success, result.category, result.model_available),
                         (False, "invalid_response", None))
        self.assertNotIn("not-json", repr(result))
        self.assertNotIn("xai-ABCDEFGHIJKLMNOPQRSTUVWX", repr(result))

    async def test_model_list_check_sanitizes_http_error_details(self) -> None:
        async def respond(_: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"error": {
                "code": "permission_denied",
                "message": "Bearer mock-key cannot access team private-team",
            }})

        result = await check_xai_model_availability(
            config=ProviderConfig(enabled=True, xai_api_key="mock-key", xai_model="grok-4.7"),
            transport=httpx.MockTransport(respond),
        )
        self.assertEqual((result.category, result.status_code, result.provider_code),
                         ("permission_denied", 403, "permission_denied"))
        output = StringIO()
        with redirect_stdout(output):
            print(format_diagnostic_result(result))
        for private_value in ("mock-key", "private-team", "private-team-42"):
            self.assertNotIn(private_value, repr(result))
            self.assertNotIn(private_value, output.getvalue())
        self.assertEqual(result.xai_request, "models")
        self.assertEqual(result.response_content_type, "application/json")
        self.assertEqual(result.top_level_json_keys, ("error",))
        self.assertEqual(result.error_value_type, "dict")

    async def test_model_list_400_mentioning_api_key_is_credential_rejected(self) -> None:
        async def respond(_: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"message": "api key rejected"}})

        result = await check_xai_model_availability(
            config=ProviderConfig(enabled=True, xai_api_key="mock-key", xai_model="grok-4.7"),
            transport=httpx.MockTransport(respond),
        )
        self.assertEqual((result.category, result.status_code), ("credential_rejected", 400))
        self.assertEqual(result.provider_message, "Provider rejected the request.")

    async def test_disabled_check_does_not_make_request(self) -> None:
        async def unexpected(_: httpx.Request) -> httpx.Response:
            self.fail("disabled diagnostic must not make a request")

        result = await check_provider(
            "huggingface", config=ProviderConfig(), transport=httpx.MockTransport(unexpected)
        )
        self.assertEqual((result.success, result.category), (False, "disabled"))


if __name__ == "__main__":
    unittest.main()
