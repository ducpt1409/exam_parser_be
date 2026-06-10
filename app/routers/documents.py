"""Router tài liệu — upload → chuyển tiếp AI service → trả exam_id.

POC: BE STATELESS — không lưu job riêng. AI service xử lý + tự lưu kết quả vào store
`exam_parser` (Mongo/MinIO của AI); BE chỉ forward file rồi trả `exam_id` để client
gọi tiếp GET /api/v1/exams/{exam_id} lấy chi tiết. Lịch sử = GET /api/v1/exams.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.clients.ai_client import AIClient, get_ai_client
from app.core.config import settings
from app.core.logging import logger
from app.schemas.common import UploadResponse

router = APIRouter()


@router.post("/documents", response_model=UploadResponse,
             summary="Upload đề thi → chuyển tiếp AI service → trả exam_id")
async def upload_document(
    file: UploadFile = File(...),
    ai: AIClient = Depends(get_ai_client),
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

    # Chuyển tiếp sang AI service (đồng bộ) — AI xử lý + lưu store exam_parser,
    # chỉ trả exam_id khi thành công.
    logger.info(f"[BE] upload {filename} ({size} bytes) → AI service")
    result = await ai.parse(filename, content, file.content_type or "application/pdf")
    logger.info(f"[BE] AI trả về ok={result.ok} exam_id={result.exam_id} err={result.error_code}")

    # Client dùng exam_id gọi tiếp GET /api/v1/exams/{exam_id} để lấy chi tiết đề
    return UploadResponse(
        status="done" if result.ok else "failed",
        exam_id=result.exam_id,
        error_code=result.error_code,
        stage=result.stage,
        message=result.message or ("Đã xử lý xong" if result.ok else "Xử lý lỗi"),
    )
