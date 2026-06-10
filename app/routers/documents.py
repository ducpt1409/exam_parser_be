"""Router tài liệu — upload → chuyển tiếp AI service → lưu job → trả trạng thái.

Chế độ ĐỒNG BỘ (POC): chờ AI xử lý xong rồi trả. Đã tách hàm để sau nâng cấp bất đồng bộ.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.clients.ai_client import AIClient, get_ai_client
from app.core.config import settings
from app.core.logging import logger
from app.repositories.job_repo import get_job_repo
from app.schemas.job import JobListResponse, UploadResponse
from app.services.job_service import JobService

router = APIRouter()


def get_job_service() -> JobService:
    return JobService(get_job_repo())


@router.post("/documents", response_model=UploadResponse,
             summary="Upload đề thi → chuyển tiếp AI service → lưu job + trả exam_id")
async def upload_document(
    file: UploadFile = File(...),
    ai: AIClient = Depends(get_ai_client),
    svc: JobService = Depends(get_job_service),
):
    filename = file.filename or "upload"
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_ext_set:
        raise HTTPException(
            status_code=415,
            detail=f"Định dạng '{ext}' không hỗ trợ. Chỉ nhận: {sorted(settings.allowed_ext_set)}",
        )

    content = await file.read()
    await file.close()

    size = len(content)
    if size == 0:
        raise HTTPException(status_code=422, detail="File rỗng (0 byte)")
    if size > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File {size / 1024 / 1024:.1f}MB vượt giới hạn {settings.max_upload_mb}MB",
        )

    # 1. Tạo job processing
    job = svc.create(filename, file.content_type or "application/pdf", size)
    logger.info(f"[BE] job {job.id} created cho {filename} ({size} bytes)")

    # 2. Chuyển tiếp sang AI service (đồng bộ) — AI chỉ trả exam_id khi thành công
    result = await ai.parse(filename, content, file.content_type or "application/pdf")

    # 3. Cập nhật job theo kết quả
    job = svc.finalize(job, result)
    logger.info(f"[BE] job {job.id} → {job.status} (exam_id={job.exam_id}, err={job.error_code})")

    # Client dùng exam_id gọi tiếp GET /api/v1/exams/{exam_id} để lấy chi tiết đề
    return UploadResponse(
        job_id=job.id,
        status=job.status,
        exam_id=job.exam_id,
        error_code=job.error_code,
        stage=job.stage,
        message=(result.message or "Đã xử lý xong") if result.ok else (result.message or "Xử lý lỗi"),
    )


@router.get("/documents/{job_id}", summary="Xem 1 job")
async def get_document(job_id: str, svc: JobService = Depends(get_job_service)):
    job = svc.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy job {job_id}")
    return job


@router.get("/documents", response_model=JobListResponse, summary="List job (mới nhất trước)")
async def list_documents(
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    svc: JobService = Depends(get_job_service),
):
    total, items = svc.list(limit=limit, skip=skip)
    return JobListResponse(total=total, items=items)
