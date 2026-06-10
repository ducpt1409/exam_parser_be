"""exam_parser_be — Backend service.

Lớp proxy + nghiệp vụ: nhận file đề thi từ client → chuyển tiếp AI service
(exam_parser_paddle hoặc exam_parser_mineru — API giống nhau) → lưu lịch sử job →
trả trạng thái. Đổi AI = đổi AI_SERVICE_URL (không sửa code).

Chạy local:
    uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
Docker: xem README.md
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.clients.ai_client import get_ai_client
from app.core.config import settings
from app.core.logging import logger
from app.repositories.job_repo import get_job_repo
from app.routers import documents, exams
from app.schemas.job import HealthResponse

app = FastAPI(
    title="exam_parser_be — Backend",
    description="BE chuyển tiếp file đề thi sang AI service và quản lý lịch sử job",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")] or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
app.include_router(exams.router, prefix="/api/v1", tags=["exams"])


@app.get("/api/v1/health", response_model=HealthResponse)
async def health():
    ai = get_ai_client()
    ai_ok = await ai.health()
    try:
        mongo_ok = get_job_repo().ping()
    except Exception:
        mongo_ok = False
    return HealthResponse(
        status="ok",
        ai_service_url=settings.ai_service_url,
        ai_service_healthy=ai_ok,
        mongo_healthy=mongo_ok,
    )


@app.on_event("startup")
async def startup():
    logger.info(
        f"BE start @ {settings.api_host}:{settings.api_port} "
        f"| AI={settings.ai_service_url} | Mongo={settings.mongo_uri}"
    )
