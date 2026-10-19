"""Backend-only, opt-in text-generation adapters for configured AI providers.

Provider output is returned as untrusted text. This module is intentionally not
called by the PDF, Excel, graph, audit, or clarification pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Callable

import httpx
from dotenv import load_dotenv


def _load_backend_dotenv(dotenv_path: Path) -> str:
    """Load backend settings and retain only where the xAI key was sourced."""
    key_was_in_process = "XAI_API_KEY" in os.environ
    load_dotenv(dotenv_path, override=False)
    if key_was_in_process:
        return "process_env"
    if "XAI_API_KEY" in os.environ:
        return "dotenv_file"
    return "unset"


def _key_shape(raw_key: str) -> dict[str, int | bool]:
    stripped = raw_key.strip()
    return {
        "key_length": len(stripped),
        "starts_with_xai": stripped.startswith("xai-"),
        "has_outer_whitespace": raw_key != stripped,
        "contains_non_ascii": any(ord(char) > 127 for char in raw_key),
        "contains_quotes": any(char in raw_key for char in ("'", '"')),
        "contains_inner_whitespace": any(char.isspace() for char in stripped),
    }


XAI_API_KEY_SOURCE = _load_backend_dotenv(Path(__file__).with_name(".env"))
_XAI_KEY_SHAPE = _key_shape(os.environ.get("XAI_API_KEY", ""))


class AIProviderError(RuntimeError):
    """Sanitized provider failure; never contains credentials or response bodies."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "provider_error",
        status_code: int | None = None,
        provider_code: str | None = None,
        provider_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.provider_code = provider_code
        self.provider_message = provider_message


class AIProvidersDisabledError(AIProviderError):
    pass


class AIProviderConfigurationError(AIProviderError):
    pass


class AIProviderUnavailableError(AIProviderError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    enabled: bool = False
    gemini_api_key: str = ""
    xai_api_key: str = ""
    hf_token: str = ""
    gemini_model: str = "gemini-3.8-flash"
    xai_model: str = "grok-4.7"
    hf_model: str = "Qwen/Qwen3-4B-Thinking-2507"


def load_provider_config() -> ProviderConfig:
    """Read provider configuration from backend environment/.env only."""
    import os

    return ProviderConfig(
        enabled=os.getenv("AI_PROVIDERS_ENABLED", "false").strip().lower() == "true",
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        xai_api_key=os.getenv("XAI_API_KEY", "").strip(),
        hf_token=os.getenv("HF_TOKEN", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip(),
        xai_model=os.getenv("XAI_MODEL", "grok-4.7").strip(),
        hf_model=os.getenv("HF_MODEL", "Qwen/Qwen3-4B-Thinking-2507").strip(),
    )


def _message_text(data: dict[str, Any], provider: str) -> str:
    try:
        if provider == "gemini":
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(part["text"] for part in parts if isinstance(part.get("text"), str))
        elif provider == "xAI":
            text = "".join(
                part["text"]
                for item in data["output"]
                if isinstance(item, dict) and item.get("type") == "message"
                for part in item.get("content", [])
                if isinstance(part, dict)
                and part.get("type") == "output_text"
                and isinstance(part.get("text"), str)
            )
        else:
            text = data["choices"][0]["message"]["content"]
            if isinstance(text, list):
                text = "".join(
                    part["text"] for part in text
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                )
        if isinstance(text, str) and text.strip():
            return text.strip()
    except (AttributeError, KeyError, IndexError, TypeError):
        pass
    raise AIProviderUnavailableError(f"{provider} returned an unsupported or empty response.", category="invalid_response")


_SAFE_ERROR_CODES = {
    "invalid_api_key",
    "authentication_error",
    "permission_denied",
    "forbidden",
    "model_not_found",
    "invalid_model",
    "invalid_argument",
    "invalid_request_error",
    "rate_limit_exceeded",
    "rate_limit_error",
}

_GENERIC_ERROR_MESSAGES = {
    "authentication": "Authentication failed.",
    "permission_denied": "Permission denied.",
    "model_unavailable": "Model is unavailable.",
    "model_or_endpoint_not_found": "Model or endpoint was not found.",
    "request_validation": "Request validation failed.",
    "request_rejected": "Provider rejected the request.",
    "rate_limited": "Provider rate limit reached.",
    "unavailable": "Provider is temporarily unavailable.",
    "http_error": "Provider returned an HTTP error.",
}


def _safe_error_fields(
    response: httpx.Response,
) -> tuple[str | None, str | None]:
    """Return a known error code and fixed generic message; ignore provider text."""
    try:
        payload = response.json()
    except ValueError:
        return None, None
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
        return None, None
    error = payload["error"]
    raw_code = error.get("code")
    if not isinstance(raw_code, str):
        return None, None
    code = raw_code.strip().lower()
    return (code, None) if code in _SAFE_ERROR_CODES else (None, None)


def _http_error(
    provider: str,
    response: httpx.Response,
) -> AIProviderError:
    code, _ = _safe_error_fields(response)
    normalized_code = (code or "").lower()
    known_code_categories = {
        "invalid_api_key": "authentication",
        "authentication_error": "authentication",
        "permission_denied": "permission_denied",
        "forbidden": "permission_denied",
        "model_not_found": "model_unavailable",
        "invalid_model": "model_unavailable",
        "invalid_argument": "request_validation",
        "invalid_request_error": "request_validation",
        "rate_limit_exceeded": "rate_limited",
        "rate_limit_error": "rate_limited",
    }
    if response.status_code == 400:
        category = known_code_categories.get(normalized_code, "request_rejected")
    elif response.status_code == 404 and normalized_code in {"model_not_found", "invalid_model"}:
        category = "model_unavailable"
    else:
        category = {
            401: "authentication",
            403: "permission_denied",
            404: "model_or_endpoint_not_found",
            422: "request_validation",
            429: "rate_limited",
        }.get(response.status_code, "unavailable" if response.status_code >= 500 else "http_error")
    safe_message = _GENERIC_ERROR_MESSAGES.get(category, "Provider request failed.")
    message = f"{provider} request failed (HTTP {response.status_code}): {safe_message}"
    error_type = AIProviderUnavailableError if response.status_code == 429 or response.status_code >= 500 else AIProviderConfigurationError
    if response.status_code not in (400, 401, 403, 404, 422, 429) and response.status_code < 500:
        error_type = AIProviderError
    return error_type(
        message,
        category=category,
        status_code=response.status_code,
        provider_code=code,
        provider_message=safe_message,
    )


async def _post(
    provider: str,
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float,
    transport: httpx.AsyncBaseTransport | None,
    status_observer: Callable[[int], None] | None = None,
    diagnostic_observer: Callable[[httpx.Response], None] | None = None,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            response = await client.post(url, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise AIProviderUnavailableError(f"{provider} request timed out.", category="timeout") from exc
    except httpx.RequestError as exc:
        raise AIProviderUnavailableError(f"{provider} is unavailable.", category="unavailable") from exc

    if status_observer is not None:
        status_observer(response.status_code)

    if not response.is_success:
        if diagnostic_observer is not None:
            diagnostic_observer(response)
        raise _http_error(provider, response)
    try:
        data = response.json()
    except ValueError as exc:
        raise AIProviderUnavailableError(f"{provider} returned an invalid response.", category="invalid_response", status_code=response.status_code) from exc
    if not isinstance(data, dict):
        raise AIProviderUnavailableError(f"{provider} returned an invalid response.", category="invalid_response", status_code=response.status_code)
    return data


async def generate_gemini(
    prompt: str,
    *,
    config: ProviderConfig | None = None,
    timeout: float = 30.0,
    transport: httpx.AsyncBaseTransport | None = None,
    status_observer: Callable[[int], None] | None = None,
) -> str:
    cfg = config or load_provider_config()
    if not cfg.enabled:
        raise AIProvidersDisabledError("AI providers are disabled.", category="disabled")
    if not cfg.gemini_api_key:
        raise AIProviderConfigurationError("GEMINI_API_KEY is not configured.")
    if not cfg.gemini_model:
        raise AIProviderConfigurationError("GEMINI_MODEL is not configured.")
    data = await _post(
        "Gemini",
        f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.gemini_model}:generateContent",
        headers={"x-goog-api-key": cfg.gemini_api_key},
        body={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=timeout,
        transport=transport,
        status_observer=status_observer,
    )
    return _message_text(data, "gemini")


async def _generate_openai_compatible(
    provider: str,
    base_url: str,
    model: str,
    api_key: str,
    prompt: str,
    *,
    timeout: float,
    transport: httpx.AsyncBaseTransport | None,
    status_observer: Callable[[int], None] | None,
) -> str:
    if not api_key:
        env_name = "XAI_API_KEY" if provider == "xAI" else "HF_TOKEN"
        raise AIProviderConfigurationError(f"{env_name} is not configured.")
    if not model:
        raise AIProviderConfigurationError(f"{provider} model is not configured.")
    data = await _post(
        provider,
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        body={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=timeout,
        transport=transport,
        status_observer=status_observer,
    )
    return _message_text(data, provider)


async def generate_xai(
    prompt: str,
    *,
    config: ProviderConfig | None = None,
    timeout: float = 30.0,
    transport: httpx.AsyncBaseTransport | None = None,
    status_observer: Callable[[int], None] | None = None,
    diagnostic_observer: Callable[[httpx.Response], None] | None = None,
) -> str:
    cfg = config or load_provider_config()
    if not cfg.enabled:
        raise AIProvidersDisabledError("AI providers are disabled.")
    if not cfg.xai_api_key:
        raise AIProviderConfigurationError("XAI_API_KEY is not configured.")
    if not cfg.xai_model:
        raise AIProviderConfigurationError("XAI_MODEL is not configured.")
    data = await _post(
        "xAI",
        "https://api.x.ai/v1/responses",
        headers={"Authorization": f"Bearer {cfg.xai_api_key}"},
        body={"model": cfg.xai_model, "input": prompt},
        timeout=timeout,
        transport=transport,
        status_observer=status_observer,
        diagnostic_observer=diagnostic_observer,
    )
    return _message_text(data, "xAI")


async def generate_huggingface(
    prompt: str,
    *,
    config: ProviderConfig | None = None,
    timeout: float = 30.0,
    transport: httpx.AsyncBaseTransport | None = None,
    status_observer: Callable[[int], None] | None = None,
) -> str:
    cfg = config or load_provider_config()
    if not cfg.enabled:
        raise AIProvidersDisabledError("AI providers are disabled.")
    return await _generate_openai_compatible(
        "Hugging Face", "https://router.huggingface.co/v1", cfg.hf_model, cfg.hf_token, prompt,
        timeout=timeout, transport=transport, status_observer=status_observer,
    )
