from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMConfigurationError(RuntimeError):
    pass


class LLMProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenAICompatibleModelConfig:
    provider_name: str
    model_id: str
    api_key: str
    api_request_url: str
    config_id: UUID | None = None


def request_openai_compatible_reply(
    model_config: OpenAICompatibleModelConfig,
    *,
    messages: list[dict[str, Any]],
    timeout_seconds: float,
    max_tokens: int | None = None,
) -> str:
    api_key = model_config.api_key.strip()
    model_id = model_config.model_id.strip()
    api_request_url = model_config.api_request_url.strip()
    if not api_key:
        raise LLMConfigurationError("Large model API key is not configured")
    if not model_id:
        raise LLMConfigurationError("Large model id is not configured")
    if not api_request_url:
        raise LLMConfigurationError("Large model API request URL is not configured")

    payload: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    request = Request(
        url=_chat_completions_url(api_request_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise LLMProviderError(_format_http_error(error)) from error
    except URLError as error:
        raise LLMProviderError(f"Cannot connect to large model service: {error.reason}") from error
    except TimeoutError as error:
        raise LLMProviderError("Large model service response timed out") from error
    except json.JSONDecodeError as error:
        raise LLMProviderError("Large model service returned an invalid JSON response") from error

    return _extract_reply(response_payload)


def request_openai_compatible_transcription(
    model_config: OpenAICompatibleModelConfig,
    *,
    audio_content: bytes,
    file_name: str,
    content_type: str,
    timeout_seconds: float,
    language: str = "zh",
) -> str:
    api_key = model_config.api_key.strip()
    model_id = model_config.model_id.strip()
    api_request_url = model_config.api_request_url.strip()
    if not api_key:
        raise LLMConfigurationError("Large model API key is not configured")
    if not model_id:
        raise LLMConfigurationError("Transcription model id is not configured")
    if not api_request_url:
        raise LLMConfigurationError("Large model API request URL is not configured")
    if not audio_content:
        raise LLMProviderError("Audio content is empty")

    boundary = f"canwen-{uuid.uuid4().hex}"
    body = _multipart_body(
        boundary=boundary,
        fields={
            "model": model_id,
            "language": language,
        },
        files=[
            {
                "name": "file",
                "file_name": file_name or "voice.webm",
                "content_type": content_type or "application/octet-stream",
                "content": audio_content,
            }
        ],
    )
    request = Request(
        url=_audio_transcriptions_url(api_request_url),
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise LLMProviderError(_format_http_error(error)) from error
    except URLError as error:
        raise LLMProviderError(f"Cannot connect to large model service: {error.reason}") from error
    except TimeoutError as error:
        raise LLMProviderError("Large model service response timed out") from error
    except json.JSONDecodeError as error:
        raise LLMProviderError("Large model service returned an invalid JSON response") from error

    return _extract_transcription_text(response_payload)


def _chat_completions_url(api_request_url: str) -> str:
    normalized_url = api_request_url.strip().rstrip("/")
    if normalized_url.endswith("/chat/completions"):
        return normalized_url
    return f"{normalized_url}/chat/completions"


def _audio_transcriptions_url(api_request_url: str) -> str:
    normalized_url = api_request_url.strip().rstrip("/")
    if normalized_url.endswith("/audio/transcriptions"):
        return normalized_url
    return f"{normalized_url}/audio/transcriptions"


def _multipart_body(*, boundary: str, fields: dict[str, str], files: list[dict[str, Any]]) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{_escape_multipart_value(name)}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for file in files:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    'Content-Disposition: form-data; '
                    f'name="{_escape_multipart_value(str(file["name"]))}"; '
                    f'filename="{_escape_multipart_value(str(file["file_name"]))}"\r\n'
                ).encode("utf-8"),
                f'Content-Type: {file["content_type"]}\r\n\r\n'.encode("utf-8"),
                file["content"],
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks)


def _escape_multipart_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", "")


def _extract_reply(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            text = "".join(_content_part_text(part) for part in content).strip()
            if text:
                return text
        reasoning_content = message.get("reasoning_content") if isinstance(message, dict) else None
        if isinstance(reasoning_content, str) and reasoning_content.strip():
            return reasoning_content.strip()
        text = first_choice.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        delta = first_choice.get("delta")
        delta_content = delta.get("content") if isinstance(delta, dict) else None
        if isinstance(delta_content, str) and delta_content.strip():
            return delta_content.strip()

    for key in ("output_text", "response", "result", "content", "text"):
        value = response_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    data = response_payload.get("data")
    if isinstance(data, dict):
        try:
            return _extract_reply(data)
        except LLMProviderError:
            pass
    if isinstance(data, list) and data and isinstance(data[0], dict):
        for key in ("content", "text", "message"):
            value = data[0].get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    raise LLMProviderError(f"Large model service did not return a usable reply. {_response_shape_summary(response_payload)}")


def _extract_transcription_text(response_payload: dict[str, Any]) -> str:
    for key in ("text", "transcript", "output_text", "content"):
        value = response_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    data = response_payload.get("data")
    if isinstance(data, dict):
        try:
            return _extract_transcription_text(data)
        except LLMProviderError:
            pass

    raise LLMProviderError(
        f"Large model service did not return a usable transcription. {_response_shape_summary(response_payload)}"
    )


def _content_part_text(part: Any) -> str:
    if isinstance(part, str):
        return part
    if not isinstance(part, dict):
        return ""
    text = part.get("text")
    if isinstance(text, dict):
        nested_value = text.get("value")
        return nested_value if isinstance(nested_value, str) else ""
    return text if isinstance(text, str) else ""


def _response_shape_summary(response_payload: dict[str, Any]) -> str:
    summary_parts = [f"top-level keys: {', '.join(response_payload.keys()) or 'none'}"]
    choices = response_payload.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            summary_parts.append(f"choice keys: {', '.join(first_choice.keys()) or 'none'}")
            message = first_choice.get("message")
            if isinstance(message, dict):
                summary_parts.append(f"message keys: {', '.join(message.keys()) or 'none'}")

    for key in ("error", "message", "msg", "detail"):
        value = response_payload.get(key)
        if isinstance(value, str) and value.strip():
            summary_parts.append(f"{key}: {value[:180]}")
        elif isinstance(value, dict):
            nested_message = value.get("message") or value.get("msg") or value.get("detail")
            if isinstance(nested_message, str) and nested_message.strip():
                summary_parts.append(f"{key}: {nested_message[:180]}")
    return "; ".join(summary_parts)


def _format_http_error(error: HTTPError) -> str:
    try:
        raw_body = error.read().decode("utf-8")
        body = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raw_body = ""
        body = None

    detail = ""
    if isinstance(body, dict):
        provider_error = body.get("error")
        if isinstance(provider_error, dict):
            message = provider_error.get("message")
            detail = message if isinstance(message, str) else ""
        elif isinstance(body.get("detail"), str):
            detail = body["detail"]

    if not detail:
        detail = raw_body.strip() if raw_body else error.reason
    return f"Large model service returned {error.code}: {detail}"
