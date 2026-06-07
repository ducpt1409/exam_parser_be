"""Schema cho 2 API lịch sử đề (đọc từ store của AI service)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ExamSummary(BaseModel):
    """Thông tin cơ bản 1 đề (cho list, không kèm output)."""
    exam_id: str
    source_file: str = ""
    status: str = "done"
    created_at: str = ""
    n_pages: int = 0
    n_questions: int = 0
    n_groups: int = 0
    n_mcq: int = 0
    n_essay: int = 0
    bucket: str = ""
    minio_prefix: str = ""

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "ExamSummary":
        return cls(
            exam_id=str(doc.get("_id") or doc.get("exam_id", "")),
            source_file=doc.get("source_file", ""),
            status=doc.get("status", "done"),
            created_at=doc.get("created_at", ""),
            n_pages=doc.get("n_pages", 0),
            n_questions=doc.get("n_questions", 0),
            n_groups=doc.get("n_groups", 0),
            n_mcq=doc.get("n_mcq", 0),
            n_essay=doc.get("n_essay", 0),
            bucket=doc.get("bucket", ""),
            minio_prefix=doc.get("minio_prefix", ""),
        )


class ExamListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ExamSummary] = Field(default_factory=list)


class ExamDetailResponse(BaseModel):
    """Chi tiết 1 đề: thông tin cơ bản + output đầy đủ (ảnh đã nhúng base64 data URI)."""
    exam_id: str
    source_file: str = ""
    status: str = "done"
    created_at: str = ""
    n_pages: int = 0
    n_questions: int = 0
    n_groups: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Toàn bộ cấu trúc Exam; mỗi ảnh được bổ sung field "data_uri" (base64) cạnh minio_key.
    output: dict[str, Any] = Field(default_factory=dict)
    images_embedded: int = 0    # số ảnh đã nhúng base64 thành công
