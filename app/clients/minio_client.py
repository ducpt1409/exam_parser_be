"""MinIO client (read-only) — lấy bytes ảnh crop theo key để convert base64.

BE không dùng presigned URL của AI (URL đó ký theo host nội bộ `minio:9000`, không tải
được từ ngoài). Thay vào đó BE kết nối thẳng MinIO bằng key và đọc object bytes.
"""
from __future__ import annotations

import base64
from typing import Optional

from minio import Minio

from app.core.config import settings
from app.core.logging import logger


class MinioStorage:
    def __init__(self):
        self.bucket = settings.minio_bucket
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def get_bytes(self, key: str) -> Optional[bytes]:
        """Đọc object → bytes. Lỗi → None (log)."""
        resp = None
        try:
            resp = self.client.get_object(self.bucket, key)
            return resp.read()
        except Exception as e:
            logger.warning(f"[MinIO] đọc lỗi key={key} — {e}")
            return None
        finally:
            if resp is not None:
                resp.close()
                resp.release_conn()

    def get_data_uri(self, key: str, content_type: str = "image/png") -> Optional[str]:
        """Đọc object → data URI base64 (dùng thẳng cho <img src>)."""
        data = self.get_bytes(key)
        if data is None:
            return None
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{content_type};base64,{b64}"


_storage: Optional[MinioStorage] = None


def get_storage() -> MinioStorage:
    global _storage
    if _storage is None:
        _storage = MinioStorage()
    return _storage
