from __future__ import annotations

import hashlib
import mimetypes
import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import BinaryIO

from app.config import Settings, get_settings


@dataclass(frozen=True)
class StoredKnowledgeObject:
    uri: str
    sha256: str
    size: int
    content_type: str


def safe_filename(value: str) -> str:
    name = Path(value.replace("\\", "/")).name.strip().replace("\x00", "")
    if not name or name in {".", ".."}:
        raise ValueError("文件名无效")
    return name


class KnowledgeStorage:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.backend = self.settings.knowledge_storage_backend.lower().strip()
        if self.backend not in {"local", "s3"}:
            raise ValueError("knowledge_storage_backend must be local or s3")
        self.root = self.settings.knowledge_storage_root.resolve()

    def put_bytes(self, object_key: str, content: bytes, content_type: str | None = None) -> StoredKnowledgeObject:
        with SpooledTemporaryFile(max_size=16 * 1024 * 1024) as stream:
            stream.write(content)
            stream.seek(0)
            return self.put_stream(object_key, stream, content_type=content_type)

    def put_path(self, object_key: str, source_path: Path, content_type: str | None = None) -> StoredKnowledgeObject:
        with source_path.open("rb") as stream:
            return self.put_stream(object_key, stream, content_type=content_type or mimetypes.guess_type(source_path.name)[0])

    def put_stream(self, object_key: str, stream: BinaryIO, content_type: str | None = None) -> StoredKnowledgeObject:
        key = self._safe_key(object_key)
        media_type = content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"
        digest = hashlib.sha256()
        size = 0
        with SpooledTemporaryFile(max_size=32 * 1024 * 1024) as spool:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > self.settings.knowledge_upload_max_bytes:
                    raise ValueError("文件超过知识库上传大小限制")
                digest.update(chunk)
                spool.write(chunk)
            spool.seek(0)
            if self.backend == "s3":
                uri = self._put_s3(key, spool, media_type)
            else:
                uri = self._put_local(key, spool)
        return StoredKnowledgeObject(uri=uri, sha256=digest.hexdigest(), size=size, content_type=media_type)

    def read_bytes(self, uri: str) -> bytes:
        if uri.startswith("local://"):
            path = self._resolve_local_uri(uri)
            return path.read_bytes()
        if uri.startswith("s3://"):
            bucket, key = uri[5:].split("/", 1)
            client = self._s3_client()
            response = client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        raise ValueError("不支持的知识文件 URI")

    def read_text(self, uri: str) -> str:
        return self.read_bytes(uri).decode("utf-8-sig")

    def materialize(self, uri: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if uri.startswith("local://"):
            source = self._resolve_local_uri(uri)
            shutil.copyfile(source, destination)
        else:
            destination.write_bytes(self.read_bytes(uri))
        return destination

    def delete(self, uri: str) -> None:
        if uri.startswith("local://"):
            self._resolve_local_uri(uri).unlink(missing_ok=True)
            return
        if uri.startswith("s3://"):
            bucket, key = uri[5:].split("/", 1)
            self._s3_client().delete_object(Bucket=bucket, Key=key)
            return
        raise ValueError("不支持的知识文件 URI")

    def _put_local(self, key: str, stream: BinaryIO) -> str:
        destination = (self.root / key).resolve()
        if self.root != destination and self.root not in destination.parents:
            raise ValueError("知识文件路径越界")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".uploading")
        with temporary.open("wb") as output:
            shutil.copyfileobj(stream, output, length=1024 * 1024)
        temporary.replace(destination)
        return f"local://{key}"

    def _put_s3(self, key: str, stream: BinaryIO, content_type: str) -> str:
        bucket = self.settings.storage_bucket
        if not bucket:
            raise RuntimeError("S3 文档存储缺少 bucket 配置")
        self._s3_client().upload_fileobj(stream, bucket, key, ExtraArgs={"ContentType": content_type})
        return f"s3://{bucket}/{key}"

    def _s3_client(self):
        required = (
            self.settings.storage_endpoint_url,
            self.settings.storage_access_key_id,
            self.settings.storage_secret_access_key,
            self.settings.storage_bucket,
            self.settings.storage_region,
        )
        if not all(required):
            raise RuntimeError("S3 文档存储配置不完整")
        import boto3

        return boto3.client(
            "s3",
            endpoint_url=self.settings.storage_endpoint_url,
            aws_access_key_id=self.settings.storage_access_key_id,
            aws_secret_access_key=self.settings.storage_secret_access_key,
            region_name=self.settings.storage_region,
        )

    def _resolve_local_uri(self, uri: str) -> Path:
        key = self._safe_key(uri.removeprefix("local://"))
        path = (self.root / key).resolve()
        if self.root != path and self.root not in path.parents:
            raise ValueError("知识文件路径越界")
        return path

    @staticmethod
    def _safe_key(value: str) -> str:
        normalized = value.replace("\\", "/").strip("/")
        parts = [part for part in normalized.split("/") if part]
        if not parts or any(part in {".", ".."} for part in parts):
            raise ValueError("对象键无效")
        return "/".join(parts)
