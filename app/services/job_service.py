"""Nghiệp vụ job — tạo, hoàn tất (theo kết quả AI), đọc, list.

Không gọi AI trực tiếp ở đây quá nhiều — orchestration nằm ở router. Service lo phần
dựng/cập nhật bản ghi job để dễ test và sau này chuyển sang chế độ bất đồng bộ.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.clients.ai_client import AIParseResult
from app.repositories.job_repo import JobRepository
from app.schemas.job import Job, JobStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobService:
    def __init__(self, repo: JobRepository):
        self.repo = repo

    # ------------------------------------------------------------
    def create(self, filename: str, content_type: str, size_bytes: int) -> Job:
        """Tạo job mới trạng thái processing."""
        now = _now()
        job = Job(
            id=uuid4().hex,
            filename=filename,
            content_type=content_type or "application/pdf",
            size_bytes=size_bytes,
            status=JobStatus.PROCESSING,
            created_at=now,
            updated_at=now,
        )
        self.repo.save(job)
        return job

    def finalize(self, job: Job, result: AIParseResult) -> Job:
        """Cập nhật job theo kết quả AI service."""
        if result.ok:
            job.status = JobStatus.DONE
            job.exam_id = result.exam_id
            job.n_pages = result.n_pages
            job.n_questions = result.n_questions
            job.n_groups = result.n_groups
            job.bucket = result.bucket
            job.minio_prefix = result.minio_prefix
            job.stage = None
            job.error_code = None
            job.detail = ""
        else:
            job.status = JobStatus.FAILED
            job.exam_id = result.exam_id
            job.stage = result.stage
            job.error_code = result.error_code
            job.detail = result.detail or result.message
        job.updated_at = _now()
        self.repo.save(job)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.repo.get(job_id)

    def list(self, limit: int = 50, skip: int = 0):
        return self.repo.list(limit=limit, skip=skip)
