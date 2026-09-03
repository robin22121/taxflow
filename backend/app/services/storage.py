"""Object storage abstraction.

Production: NCP Object Storage (S3-compatible, endpoint ``kr.object.ncloudstorage.com``).
Dev: ``LocalFileStorage`` writes to ``backend/data/uploads/`` so we don't need credentials.

Used for:
- 거래처가 업로드한 통화 녹음 파일 (→ STT 입력)
- 거래처가 업로드한 엑셀/이미지 (→ Claude Vision 입력)
- 위하고T 표준 엑셀의 보관본 (감사 로그용)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.config import get_settings

logger = logging.getLogger(__name__)


class ObjectStorage(ABC):
    name: str

    @abstractmethod
    def put_object(self, key: str, body: bytes, content_type: str | None = None) -> str:
        """Store object, return canonical URL."""

    @abstractmethod
    def get_object(self, key: str) -> bytes: ...

    @abstractmethod
    def presign_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate presigned URL for a single GET (used by STT/Vision providers)."""

    def make_key(self, kind: str, ext: str = "") -> str:
        ts = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        return f"{kind}/{ts}/{uuid4().hex}{ext}"


class LocalFileStorage(ObjectStorage):
    """Filesystem fallback for dev / tests."""

    name = "local"

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base = Path(base_dir or "data/uploads").resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def put_object(self, key: str, body: bytes, content_type: str | None = None) -> str:
        path = self.base / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return f"file://{path}"

    def get_object(self, key: str) -> bytes:
        return (self.base / key).read_bytes()

    def presign_url(self, key: str, expires_in: int = 3600) -> str:
        # No security in local; return file URL.
        return f"file://{(self.base / key).resolve()}"


class NcpObjectStorage(ObjectStorage):
    """NCP Object Storage via boto3 (S3-compatible)."""

    name = "ncp_object_storage"

    def __init__(self) -> None:
        import boto3  # local import: keep boto3 cold for dev

        s = get_settings()
        if not (s.ncp_object_storage_access_key and s.ncp_object_storage_secret_key):
            raise RuntimeError("NCP_OBJECT_STORAGE_* 자격증명이 설정되지 않았습니다")
        self.bucket = s.ncp_object_storage_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=s.ncp_object_storage_endpoint,
            region_name=s.ncp_object_storage_region,
            aws_access_key_id=s.ncp_object_storage_access_key,
            aws_secret_access_key=s.ncp_object_storage_secret_key,
        )

    def put_object(self, key: str, body: bytes, content_type: str | None = None) -> str:
        kwargs: dict = {"Bucket": self.bucket, "Key": key, "Body": body}
        if content_type:
            kwargs["ContentType"] = content_type
        self.client.put_object(**kwargs)
        s = get_settings()
        return f"{s.ncp_object_storage_endpoint}/{self.bucket}/{key}"

    def get_object(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def presign_url(self, key: str, expires_in: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )


def get_storage() -> ObjectStorage:
    s = get_settings()
    if s.ncp_object_storage_access_key and s.ncp_object_storage_secret_key:
        return NcpObjectStorage()
    # 1순위: UPLOAD_DIR env로 명시된 영속 경로 (NHN vm-node 운영 기본)
    if s.upload_dir:
        logger.info("[storage] Using UPLOAD_DIR at %s", s.upload_dir)
        return LocalFileStorage(base_dir=s.upload_dir)
    # 2순위(하위호환): 관례상 /data/uploads가 마운트돼 있으면 사용
    legacy_disk = Path("/data/uploads")
    if legacy_disk.is_dir():
        logger.info("[storage] Using persistent disk at %s", legacy_disk)
        return LocalFileStorage(base_dir=legacy_disk)
    # fallback: 상대경로 data/uploads (로컬 개발/임시 — 영속·백업 보장 안 됨)
    logger.warning(
        "[storage] UPLOAD_DIR unset and /data/uploads not found — "
        "falling back to relative data/uploads (dev/ephemeral)."
    )
    return LocalFileStorage()


__all__ = ["LocalFileStorage", "NcpObjectStorage", "ObjectStorage", "get_storage"]
