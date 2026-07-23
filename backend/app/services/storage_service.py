from __future__ import annotations

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
import boto3
import logging

from fastapi import HTTPException, status

from app.core.config import get_settings


settings = get_settings()
logger = logging.getLogger(__name__)


def upload_public_file(*, object_key: str, content: bytes, content_type: str) -> str:
    return upload_object_file(
        object_key=object_key,
        content=content,
        content_type=content_type,
        failure_detail="头像上传失败，请稍后再试",
    )


def upload_object_file(*, object_key: str, content: bytes, content_type: str, failure_detail: str = "文件上传失败，请稍后再试") -> str:
    _ensure_storage_configured()

    try:
        client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint_url,
            aws_access_key_id=settings.storage_access_key_id,
            aws_secret_access_key=settings.storage_secret_access_key,
            region_name=settings.storage_region,
            config=Config(
                signature_version="s3",
                s3={"addressing_style": "virtual"},
            ),
        )
        client.put_object(
            Bucket=settings.storage_bucket,
            Key=object_key,
            Body=content,
            ContentType=content_type,
        )
    except ClientError as exc:
        error = exc.response.get("Error", {})
        logger.warning(
            "object storage upload failed: key=%s code=%s message=%s",
            object_key,
            error.get("Code"),
            error.get("Message"),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=failure_detail,
        ) from exc
    except BotoCoreError as exc:
        logger.warning("object storage upload failed: key=%s error=%s", object_key, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=failure_detail,
        ) from exc

    return _public_url_for_key(object_key)


def delete_object_file(*, object_key: str, failure_detail: str = "文件删除失败，请稍后再试") -> None:
    _ensure_storage_configured()

    try:
        client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint_url,
            aws_access_key_id=settings.storage_access_key_id,
            aws_secret_access_key=settings.storage_secret_access_key,
            region_name=settings.storage_region,
            config=Config(
                signature_version="s3",
                s3={"addressing_style": "virtual"},
            ),
        )
        client.delete_object(Bucket=settings.storage_bucket, Key=object_key)
    except ClientError as exc:
        error = exc.response.get("Error", {})
        logger.warning(
            "object storage delete failed: key=%s code=%s message=%s",
            object_key,
            error.get("Code"),
            error.get("Message"),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=failure_detail,
        ) from exc
    except BotoCoreError as exc:
        logger.warning("object storage delete failed: key=%s error=%s", object_key, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=failure_detail,
        ) from exc


def is_storage_configured() -> bool:
    return all(value and value.strip() for value in _storage_config_values())


def _ensure_storage_configured() -> None:
    if not is_storage_configured():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="对象存储未配置",
        )


def _storage_config_values() -> tuple[str | None, ...]:
    return (
        settings.storage_endpoint_url,
        settings.storage_access_key_id,
        settings.storage_secret_access_key,
        settings.storage_bucket,
        settings.storage_region,
        settings.storage_public_base_url,
    )


def _public_url_for_key(object_key: str) -> str:
    public_base_url = settings.storage_public_base_url or ""
    return f"{public_base_url.rstrip('/')}/{object_key.lstrip('/')}"
