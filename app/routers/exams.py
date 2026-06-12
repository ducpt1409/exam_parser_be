"""Router lịch sử đề — 4 API cho FE.

GET    /api/v1/exams                    : list lịch sử (lọc exam_id/source_file, phân trang)
GET    /api/v1/exams/{exam_id}          : chi tiết 1 đề (output đầy đủ + ảnh nhúng base64)
GET    /api/v1/exams/{exam_id}/download : tải toàn bộ thư mục dữ liệu đề trên MinIO (zip)
DELETE /api/v1/exams/{exam_id}          : xoá đề — toàn bộ file MinIO + bản ghi Mongo
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from app.schemas.exam import ExamDetailResponse, ExamListResponse
from app.services.exam_service import ExamDeleteError, ExamService, get_exam_service

router = APIRouter()


@router.get("/exams", response_model=ExamListResponse,
            summary="List lịch sử đề (lọc + phân trang)")
async def list_exams(
    exam_id: Optional[str] = Query(None, description="Lọc theo exam_id (chứa, không phân biệt hoa thường)"),
    source_file: Optional[str] = Query(None, description="Lọc theo tên file gốc (chứa)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: ExamService = Depends(get_exam_service),
):
    return svc.list(exam_id=exam_id, source_file=source_file, page=page, page_size=page_size)


@router.get("/exams/{exam_id}", response_model=ExamDetailResponse,
            summary="Chi tiết 1 đề (ảnh đã convert base64)")
async def get_exam_detail(
    exam_id: str,
    svc: ExamService = Depends(get_exam_service),
):
    detail = svc.get_detail(exam_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy đề {exam_id}")
    return detail


@router.get("/exams/{exam_id}/download",
            summary="Tải toàn bộ thư mục dữ liệu đề thi trên MinIO về (file zip)")
async def download_exam_data(
    exam_id: str,
    svc: ExamService = Depends(get_exam_service),
):
    # Nén nhiều file từ MinIO là việc nặng I/O → chạy ở thread riêng, không chặn event loop
    result = await asyncio.to_thread(svc.build_zip, exam_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy đề {exam_id} hoặc đề không có dữ liệu trên MinIO",
        )
    filename, buf = result
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/exams/{exam_id}",
               summary="Xoá 1 đề: toàn bộ file trên MinIO + bản ghi Mongo (báo lỗi theo bước)")
async def delete_exam(
    exam_id: str,
    svc: ExamService = Depends(get_exam_service),
):
    """Xoá theo bước: lookup → minio_list → minio_delete → mongo_delete.

    Lỗi bước nào trả body dừng ở bước đó:
    `{status: failed, exam_id, stage, error_code, message, detail}`
    (BE404 lookup không thấy | BE510 lookup/minio_list | BE511 minio_delete | BE512 mongo_delete).
    """
    try:
        # Xoá nhiều object MinIO là việc nặng I/O → chạy ở thread riêng
        result = await asyncio.to_thread(svc.delete, exam_id)
    except ExamDeleteError as err:
        http_status = 404 if err.error_code == "BE404" else 502
        return JSONResponse(status_code=http_status, content={
            "status": "failed",
            "exam_id": exam_id,
            "stage": err.stage,
            "error_code": err.error_code,
            "message": err.message,
            "detail": err.detail,
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "status": "failed",
            "exam_id": exam_id,
            "stage": "unknown",
            "error_code": "BE500",
            "message": "Lỗi không xác định khi xoá đề",
            "detail": str(e),
        })

    return {
        "status": "deleted",
        "exam_id": exam_id,
        "files_deleted": result["files_deleted"],
        "message": f"Đã xoá đề {exam_id}: {result['files_deleted']} file MinIO + bản ghi Mongo",
    }
