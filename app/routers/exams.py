"""Router lịch sử đề — 2 API cho FE.

GET /api/v1/exams           : list lịch sử (lọc exam_id/source_file, phân trang)
GET /api/v1/exams/{exam_id} : chi tiết 1 đề (output đầy đủ + ảnh nhúng base64)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.exam import ExamDetailResponse, ExamListResponse
from app.services.exam_service import ExamService, get_exam_service

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
