"""Schema response chung của BE (POC: BE stateless, không lưu job riêng)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class UploadResponse(BaseModel):
    """Trả về client sau khi upload — chỉ trạng thái + id; client (FE/mobile) dùng
    `exam_id` gọi tiếp GET /api/v1/exams/{exam_id} để lấy chi tiết đề.

    Lịch sử = chính các bản ghi trong store `exam_parser` của AI service
    (GET /api/v1/exams) — BE không lưu gì thêm.
    """
    status: str                       # done | failed
    exam_id: Optional[str] = None
    error_code: Optional[str] = None
    stage: Optional[str] = None
    message: str = ""


class HealthResponse(BaseModel):
    status: str = "ok"
    ai_service_url: str = ""
    ai_service_healthy: bool = False
    mongo_healthy: bool = False       # Mongo của AI service (store exam_parser)
