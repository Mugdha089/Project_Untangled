"""Opt-in, backend-only credential smoke checks with sanitized output."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import re
from typing import Awaitable, Callable

import httpx

import ai_providers
from ai_providers import (
    AIProviderConfigurationError,
    AIProviderError,
    AIProviderUnavailableError,
    AIProvidersDisabledError,
    ProviderConfig,
    XAI_API_KEY_SOURCE,
    _http_error,
    generate_gemini,
    generate_huggingface,
    generate_xai,
    load_provider_config,
)


@dataclass(frozen=True)
class DiagnosticResult:
    provider: str
    success: bool
    category: str
    status_code: int | None = None
    provider_code: str | None = None
    provider_message: str | None = None
    model_available: bool | None = None
    xai_request: str | None = None
    response_content_type: str | None = None
    body_length_bytes: int | None = None
    top_level_json_keys: tuple[str, ...] | None = None
    error_value_type: str | None = None
    mentions_api_key: bool | None = None
    mentions_model: bool | None = None
    mentions_permission: bool | None = None
    xai_key_length: int | None = None
    xai_key_starts_with_prefix: bool | None = None
    xai_key_has_outer_whitespace: bool | None = None
    xai_key_contains_non_ascii: bool | None = None
    xai_key_contains_quotes: bool | None = None
    xai_key_contains_inner_whitespace: bool | None = None
    xai_key_source: str | None = None


_SAFE_JSON_KEYS = {"error", "code", "message", "type", "param", "data", "object", "id"}
_BODY_PHRASES = (
    ("mentions_api_key", b"api key"),
    ("mentions_model", b"model"),
    ("mentions_permission", b"permission"),
)


def _xai_key_metadata(request_kind: str) -> dict[str, object]:
    shape = ai_providers._XAI_KEY_SHAPE
    return {
        "xai_request": request_kind,
        "response_content_type": None,
        "body_length_bytes": None,
        "top_level_json_keys": None,
        "error_value_type": None,
        "mentions_api_key": None,
        "mentions_model": None,
        "mentions_permission": None,
        "xai_key_length": shape["key_length"],
        "xai_key_starts_with_prefix": shape["starts_with_xai"],
        "xai_key_has_outer_whitespace": shape["has_outer_whitespace"],
        "xai_key_contains_non_ascii": shape["contains_non_ascii"],
        "xai_key_contains_quotes": shape["contains_quotes"],
        "xai_key_contains_inner_whitespace": shape["contains_inner_whitespace"],
        "xai_key_source": XAI_API_KEY_SOURCE,
    }


def _response_diagnostics(response: httpx.Response, request_kind: str) -> dict[str, object]:
    """Extract only content-free metadata from a failed xAI response."""
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not re.fullmatch(r"[a-z0-9.+-]{1,40}/[a-z0-9.+-]{1,40}", content_type):
        content_type = "other" if content_type else "unknown"
    raw_body = response.content
    try:
        payload = response.json()
    except ValueError:
        payload = None
    keys: tuple[str, ...] | None = None
    error_type: str | None = None
    if isinstance(payload, dict):
        keys = tuple(sorted(key if key in _SAFE_JSON_KEYS else "other" for key in payload if isinstance(key, str)))
        if "error" in payload:
            error = payload["error"]
            error_type = "str" if isinstance(error, str) else "dict" if isinstance(error, dict) else "other"
    phrase_source = raw_body
    if isinstance(payload, dict):
        error_value = payload.get("error")
        if isinstance(error_value, str):
            phrase_source = error_value.encode("utf-8", errors="replace")
        elif isinstance(error_value, dict) and isinstance(error_value.get("message"), str):
            phrase_source = error_value["message"].encode("utf-8", errors="replace")
    lowered = phrase_source.lower()
    flags = {name: phrase in lowered for name, phrase in _BODY_PHRASES}
    return {
        **_xai_key_metadata(request_kind),
        "response_content_type": content_type,
        "body_length_bytes": len(raw_body),
        "top_level_json_keys": keys,
        "error_value_type": error_type,
        **flags,
    }


def format_diagnostic_result(result: DiagnosticResult) -> str:
    availability = (
        f" model_available={str(result.model_available).lower()}"
        if result.model_available is not None else ""
    )
    status = f" status={result.status_code}" if result.status_code is not None else ""
    outcome = "SUCCESS" if result.success else "FAILURE"
    safe_code = f" code={result.provider_code}" if result.provider_code else ""
    safe_message = f" message={result.provider_message}" if result.provider_message else ""
    xai_fields = ""
    if result.xai_request is not None:
        xai_fields = (
            f" request={result.xai_request} content_type={result.response_content_type}"
            f" body_bytes={result.body_length_bytes} json_keys={result.top_level_json_keys}"
            f" error_type={result.error_value_type} mentions_api_key={result.mentions_api_key}"
            f" mentions_model={result.mentions_model} mentions_permission={result.mentions_permission}"
            f" key_length={result.xai_key_length} key_starts_xai={result.xai_key_starts_with_prefix}"
            f" key_outer_whitespace={result.xai_key_has_outer_whitespace}"
            f" key_non_ascii={result.xai_key_contains_non_ascii} key_quotes={result.xai_key_contains_quotes}"
            f" key_inner_whitespace={result.xai_key_contains_inner_whitespace}"
            f" key_source={result.xai_key_source}"
        )
    return (
        f"{outcome} provider={result.provider} category={result.category}"
        f"{availability}{status}{safe_code}{safe_message}{xai_fields}"
    )


async def check_provider(
    provider: str,
    *,
    config: ProviderConfig | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> DiagnosticResult:
    """Make one short request and retain only status/category, never response text."""
    providers: dict[str, tuple[str, Callable[..., Awaitable[str]]]] = {
        "gemini": ("Gemini", generate_gemini),
        "xai": ("xAI", generate_xai),
        "huggingface": ("Hugging Face", generate_huggingface),
    }
    if provider not in providers:
        return DiagnosticResult(provider, False, "unknown_provider")
    label, generate = providers[provider]
    statuses: list[int] = []
    response_details: dict[str, object] = {}
    generate_options: dict[str, object] = {}
    if provider == "xai":
        response_details.update(_xai_key_metadata("responses"))
        generate_options["diagnostic_observer"] = lambda response: response_details.update(
            _response_diagnostics(response, "responses")
        )
    try:
        await generate(
            "Reply with the single word OK.",
            config=config,
            timeout=15.0,
            transport=transport,
            status_observer=statuses.append,
            **generate_options,
        )
        return DiagnosticResult(label, True, "ok", statuses[-1] if statuses else None)
    except AIProviderError as exc:
        if isinstance(exc, AIProvidersDisabledError):
            category = "disabled"
        elif isinstance(exc, AIProviderConfigurationError):
            category = getattr(exc, "category", "configuration")
            if category == "provider_error":
                category = "configuration"
        elif isinstance(exc, AIProviderUnavailableError):
            category = getattr(exc, "category", "unavailable")
            if category == "provider_error":
                category = "unavailable"
        else:
            category = getattr(exc, "category", "provider_error")
        if (
            provider == "xai"
            and getattr(exc, "status_code", None) == 400
            and response_details.get("mentions_api_key") is True
        ):
            category = "credential_rejected"
        return DiagnosticResult(
            label,
            False,
            category,
            getattr(exc, "status_code", None),
            getattr(exc, "provider_code", None),
            getattr(exc, "provider_message", None),
            **response_details,
        )
    except Exception:
        # Keep diagnostics safe even if a future adapter raises an unexpected error.
        return DiagnosticResult(label, False, "internal_error", **response_details)


async def check_xai_model_availability(
    *,
    config: ProviderConfig | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> DiagnosticResult:
    """Check only whether XAI_MODEL is listed for this key; never return model data."""
    cfg = config or load_provider_config()
    if not cfg.enabled:
        return DiagnosticResult("xAI models", False, "disabled")
    if not cfg.xai_api_key or not cfg.xai_model:
        return DiagnosticResult("xAI models", False, "missing_configuration")
    headers = {"Authorization": f"Bearer {cfg.xai_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=15.0, transport=transport) as client:
            response = await client.get("https://api.x.ai/v1/models", headers=headers)
    except httpx.TimeoutException:
        return DiagnosticResult("xAI models", False, "timeout")
    except httpx.RequestError:
        return DiagnosticResult("xAI models", False, "unavailable")
    if not response.is_success:
        error = _http_error("xAI models", response)
        response_details = _response_diagnostics(response, "models")
        category = (
            "credential_rejected"
            if error.status_code == 400 and response_details.get("mentions_api_key") is True
            else error.category
        )
        return DiagnosticResult(
            "xAI models", False, category, error.status_code,
            error.provider_code, error.provider_message,
            **response_details,
        )
    try:
        payload = response.json()
    except ValueError:
        return DiagnosticResult("xAI models", False, "invalid_response", response.status_code)
    records = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return DiagnosticResult("xAI models", False, "invalid_response", response.status_code)
    is_available = any(
        isinstance(record, dict)
        and (
            record.get("id") == cfg.xai_model
            or (isinstance(record.get("aliases"), list) and cfg.xai_model in record["aliases"])
        )
        for record in records
    )
    return DiagnosticResult(
        "xAI models", True, "model_available" if is_available else "model_not_listed",
        response.status_code, model_available=is_available,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely diagnose one configured AI provider.")
    parser.add_argument("provider", choices=("gemini", "xai", "huggingface", "xai-model"))
    args = parser.parse_args()
    cfg = load_provider_config()
    if args.provider == "xai-model":
        result = asyncio.run(check_xai_model_availability(config=cfg))
    else:
        result = asyncio.run(check_provider(args.provider, config=cfg))
    print(format_diagnostic_result(result))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
