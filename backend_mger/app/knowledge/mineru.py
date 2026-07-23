from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, get_settings


class MinerUError(RuntimeError):
    pass


@dataclass(frozen=True)
class MinerUBatch:
    batch_id: str
    upload_urls: list[str]


class MinerUClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.mineru_base_url.rstrip("/")
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        if not self.settings.mineru_token:
            raise MinerUError("MinerU Token 未配置")
        return {"Authorization": f"Bearer {self.settings.mineru_token}"}

    async def create_upload_batch(self, files: list[dict[str, Any]]) -> MinerUBatch:
        payload = {
            "files": files,
            "model_version": self.settings.mineru_model_version,
            "language": "ch",
            "enable_table": True,
            "enable_formula": True,
        }
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            response = await client.post(f"{self.base_url}/file-urls/batch", headers=self._headers(), json=payload)
        data = self._response_data(response)
        batch_id = str(data.get("batch_id", ""))
        urls = data.get("file_urls") or []
        if not batch_id or not isinstance(urls, list) or len(urls) != len(files):
            raise MinerUError("MinerU 未返回完整的批量上传地址")
        return MinerUBatch(batch_id=batch_id, upload_urls=[str(url) for url in urls])

    async def upload_signed_file(self, upload_url: str, path: Path) -> None:
        async def chunks():
            with path.open("rb") as stream:
                while chunk := await asyncio.to_thread(stream.read, 1024 * 1024):
                    yield chunk

        async with httpx.AsyncClient(timeout=300, transport=self.transport) as client:
            response = await client.put(upload_url, content=chunks())
        if response.status_code >= 400:
            raise MinerUError(f"MinerU 签名地址上传失败：HTTP {response.status_code}")

    async def get_batch_result(self, batch_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            response = await client.get(f"{self.base_url}/extract-results/batch/{batch_id}", headers=self._headers())
        return self._response_data(response)

    async def wait_for_batch(self, batch_id: str) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.mineru_timeout_seconds
        delay = self.settings.mineru_poll_initial_seconds
        while True:
            data = await self.get_batch_result(batch_id)
            results = data.get("extract_result") or data.get("results") or []
            states = {str(item.get("state", "")) for item in results if isinstance(item, dict)}
            if results and states <= {"done"}:
                return data
            if "failed" in states:
                failures = [str(item.get("err_msg", "解析失败")) for item in results if item.get("state") == "failed"]
                raise MinerUError("；".join(failures)[:1000])
            if loop.time() >= deadline:
                raise MinerUError("MinerU 解析任务等待超时")
            await asyncio.sleep(delay)
            delay = min(self.settings.mineru_poll_max_seconds, delay * 1.5)

    @staticmethod
    def full_zip_urls(batch_data: dict[str, Any]) -> list[str]:
        results = batch_data.get("extract_result") or batch_data.get("results") or []
        return [str(item["full_zip_url"]) for item in results if item.get("state") == "done" and item.get("full_zip_url")]

    @staticmethod
    def _response_data(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise MinerUError(f"MinerU 返回非 JSON 响应：HTTP {response.status_code}") from exc
        if response.status_code >= 400 or payload.get("code") not in {0, "0", None}:
            message = str(payload.get("msg") or payload.get("message") or f"HTTP {response.status_code}")
            raise MinerUError(f"MinerU 请求失败：{message[:500]}")
        data = payload.get("data", {})
        if not isinstance(data, dict):
            raise MinerUError("MinerU 响应 data 字段格式错误")
        return data
