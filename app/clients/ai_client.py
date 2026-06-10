"""AIClient — điểm thay thế AI service.

Mọi lời gọi tới AI service đi qua interface này. Đổi phương pháp AI khác = viết 1 impl
mới (vd GrpcAIClient) + sửa factory get_ai_client(), KHÔNG đụng router/nghiệp vụ.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import logger


@dataclass
class AIParseResult:
    """Kết quả chuẩn hoá từ AI service (đã map về dạng BE dùng chung).

    AI service chỉ trả `exam_id` khi thành công — kết quả đầy đủ đọc qua
    GET /api/v1/exams/{exam_id} (exam_repo đọc store của AI).
    """
    ok: bool
    exam_id: Optional[str] = None
    message: str = ""
    # khi lỗi:
    stage: Optional[str] = None
    error_code: Optional[str] = None
    detail: str = ""


class AIClient(ABC):
    """Hợp đồng AI service."""

    @abstractmethod
    async def parse(self, filename: str, content: bytes, content_type: str) -> AIParseResult:
        ...

    @abstractmethod
    async def health(self) -> bool:
        ...


class HttpAIClient(AIClient):
    """Gọi AI service (exam_parser_paddle hoặc exam_parser_mineru) qua HTTP:
    POST /api/v1/exams/parse. API 2 service giống nhau → chỉ cần đổi base_url."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        self.base_url = (base_url or settings.ai_service_url).rstrip("/")
        self.timeout = timeout or settings.ai_timeout

    async def parse(self, filename: str, content: bytes, content_type: str) -> AIParseResult:
        url = f"{self.base_url}/api/v1/exams/parse"
        files = {"file": (filename, content, content_type or "application/pdf")}
        logger.info(f"[AIClient] POST {url} (file={filename}, {len(content)} bytes)")
        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            try:
                r = await cli.post(url, files=files)
            except httpx.RequestError as e:
                logger.error(f"[AIClient] không gọi được AI service: {e}")
                return AIParseResult(
                    ok=False, stage="ai_unreachable", error_code="BE502",
                    message="Không gọi được AI service", detail=str(e),
                )

        ct = r.headers.get("content-type", "")
        data = r.json() if ct.startswith("application/json") else {}

        if r.status_code == 200 and data.get("status") == "done":
            return AIParseResult(
                ok=True,
                exam_id=data.get("exam_id"),
                message=data.get("message", "Đã xử lý xong"),
            )

        # Lỗi: giữ nguyên error_code + stage từ AI service để client/BE bắt theo mã
        logger.warning(f"[AIClient] AI trả lỗi HTTP={r.status_code} body={data}")
        return AIParseResult(
            ok=False,
            exam_id=data.get("exam_id"),
            stage=data.get("stage", "unknown"),
            error_code=data.get("error_code", "BE500"),
            message=data.get("message", "AI xử lý lỗi"),
            detail=data.get("detail", "") or (r.text[:500] if not data else ""),
        )

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as cli:
                r = await cli.get(f"{self.base_url}/api/v1/health")
                return r.status_code == 200
        except httpx.RequestError:
            return False


def get_ai_client() -> AIClient:
    """Factory — chỗ duy nhất quyết định dùng impl nào (dùng cho FastAPI Depends)."""
    return HttpAIClient()
