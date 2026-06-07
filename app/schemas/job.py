"""Schema job của BE — 1 lần upload tài liệu = 1 job (1 document trong `be_jobs`)."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Job(BaseModel):
    """Bản ghi job đầy đủ (lưu Mongo, _id = id)."""
    id: str
    filename: str
    content_type: str = "application/pdf"
    size_bytes: int = 0
    status: JobStatus = JobStatus.PROCESSING

    # Kết quả khi done
    exam_id: Optional[str] = None
    n_pages: int = 0
    n_questions: int = 0
    n_groups: int = 0
    bucket: str = ""
    minio_prefix: str = ""

    # Khi failed
    stage: Optional[str] = None
    error_code: Optional[str] = None
    detail: str = ""

    created_at: str
    updated_at: str

    def to_mongo_doc(self) -> dict:
        doc = self.model_dump(mode="json")
        doc["_id"] = doc.pop("id")
        return doc

    @classmethod
    def from_mongo_doc(cls, doc: dict) -> "Job":
        d = dict(doc)
        d["id"] = d.pop("_id")
        return cls(**d)


class UploadResponse(BaseModel):
    """Trả về client sau khi upload (gọn — không kèm full JSON)."""
    job_id: str
    status: JobStatus
    exam_id: Optional[str] = None
    error_code: Optional[str] = None
    stage: Optional[str] = None
    minio_prefix: Optional[str] = None
    message: str = ""


class JobListResponse(BaseModel):
    total: int
    items: list[Job] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    ai_service_url: str = ""
    ai_service_healthy: bool = False
    mongo_healthy: bool = False
