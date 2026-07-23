from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from collections.abc import Sequence
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings


T = TypeVar("T", bound=BaseModel)


class ModelGatewayError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelEndpoint:
    model_id: str
    base_url: str
    api_key: str | None


class ModelGateway:
    """Small OpenAI-compatible/DashScope gateway with redacted failures."""

    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        endpoints: dict[str, ModelEndpoint] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.transport = transport
        self.endpoints = endpoints or self._default_endpoints()

    @classmethod
    def from_database(cls, settings: Settings | None = None, session_factory=None) -> "ModelGateway":
        settings = settings or get_settings()
        if session_factory is None:
            from app.db import SessionLocal

            session_factory = SessionLocal
        gateway = cls(settings)
        try:
            from sqlalchemy import select

            from app.models import SystemModelConfig
            from app.security import decrypt_secret

            with session_factory() as db:
                rows = db.scalars(select(SystemModelConfig).where(SystemModelConfig.enabled.is_(True))).all()
                for row in rows:
                    purpose = {
                        "qa-extract": "qa",
                        "kg-extract": "kg",
                        "expert-review": "expert",
                        "embedding-primary": "embedding",
                    }.get(row.key)
                    if not purpose:
                        continue
                    key = decrypt_secret(row.api_key_ciphertext) if row.api_key_ciphertext else None
                    gateway.endpoints[purpose] = ModelEndpoint(row.model_id, row.api_base_url, key or settings.dashscope_api_key)
        except Exception:
            # Database model configuration is an override. Environment-backed
            # endpoints remain available when the registry cannot be read.
            pass
        return gateway

    @staticmethod
    def _headers(api_key: str | None) -> dict[str, str]:
        if not api_key:
            raise ModelGatewayError("DashScope API Key 未配置")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def chat_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T] | None = None,
        purpose: str = "qa",
        enable_thinking: bool = False,
        temperature: float = 0.1,
        retries: int = 2,
    ) -> T | dict[str, Any]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "enable_thinking": enable_thinking,
        }
        last_error: Exception | None = None
        endpoint = self.endpoints.get(purpose) or self.endpoints["qa"]
        payload["model"] = endpoint.model_id or model
        for attempt in range(retries + 1):
            try:
                response = await self._post(
                    f"{endpoint.base_url.rstrip('/')}/chat/completions",
                    payload,
                    endpoint.api_key,
                )
                content = response["choices"][0]["message"]["content"]
                parsed = _parse_json_content(content)
                return response_model.model_validate(parsed) if response_model else parsed
            except (KeyError, IndexError, TypeError, ValueError, ValidationError, ModelGatewayError) as exc:
                last_error = exc
                if attempt >= retries:
                    break
                payload["messages"].append(
                    {
                        "role": "user",
                        "content": "上一响应不是符合 Schema 的纯 JSON。请只返回合法 JSON 对象，不要使用 Markdown 代码块。",
                    }
                )
                await asyncio.sleep(0.5 * (attempt + 1))
        raise ModelGatewayError(f"模型未返回有效结构化数据：{str(last_error)[:500]}") from last_error

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        endpoint = self.endpoints["embedding"]
        payload = {
            "model": endpoint.model_id,
            "input": list(texts),
            "dimensions": self.settings.embedding_dimensions,
            "encoding_format": "float",
        }
        response = await self._post(
            f"{endpoint.base_url.rstrip('/')}/embeddings",
            payload,
            endpoint.api_key,
        )
        data = sorted(response.get("data", []), key=lambda item: int(item.get("index", 0)))
        vectors = [item.get("embedding") for item in data]
        if len(vectors) != len(texts) or any(not isinstance(vector, list) for vector in vectors):
            raise ModelGatewayError("Embedding 响应数量或格式不正确")
        if any(len(vector) != self.settings.embedding_dimensions for vector in vectors):
            raise ModelGatewayError("Embedding 响应维度与配置不一致")
        return vectors

    async def _post(self, url: str, payload: dict[str, Any], api_key: str | None) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.model_request_timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(url, headers=self._headers(api_key), json=payload)
        except httpx.HTTPError as exc:
            raise ModelGatewayError(f"模型服务连接失败：{exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            request_id = response.headers.get("x-request-id") or response.headers.get("x-dashscope-request-id")
            suffix = f"，request_id={request_id}" if request_id else ""
            raise ModelGatewayError(f"模型服务返回 HTTP {response.status_code}{suffix}")
        try:
            result = response.json()
        except ValueError as exc:
            raise ModelGatewayError("模型服务返回非 JSON 响应") from exc
        if not isinstance(result, dict):
            raise ModelGatewayError("模型服务响应格式错误")
        return result

    def _default_endpoints(self) -> dict[str, ModelEndpoint]:
        key = self.settings.dashscope_api_key
        chat_base = self.settings.dashscope_chat_base_url
        return {
            "qa": ModelEndpoint(self.settings.qa_model_id, chat_base, key),
            "kg": ModelEndpoint(self.settings.kg_model_id, chat_base, key),
            "expert": ModelEndpoint(self.settings.expert_model_id, chat_base, key),
            "embedding": ModelEndpoint(self.settings.embedding_model_id, chat_base, key),
        }


def _parse_json_content(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        text = "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
    else:
        text = str(content)
    cleaned = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1)
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("structured response must be an object")
    return value
