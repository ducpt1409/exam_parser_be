"""Cấu hình BE — đọc từ .env qua pydantic-settings.

Điểm cốt lõi: AI_SERVICE_URL là chỗ DUY NHẤT trỏ tới AI service. Đổi phương pháp AI
= đổi URL này (hoặc viết AIClient impl mới), không sửa router/nghiệp vụ.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- AI service (exam_parser_paddle HOẶC exam_parser_mineru — API giống nhau) ---
    ai_service_url: str = "http://localhost:8001"   # Cách B: exam_parser_mineru
    ai_timeout: float = 600.0          # giây — MinerU request đầu nạp model + xếp hàng có thể lâu

    # --- Store DUY NHẤT (POC): Mongo + MinIO của AI service (db exam_parser) ---
    # BE KHÔNG có Mongo riêng — AI service ghi, BE đọc (read-only) cho lịch sử +
    # chi tiết đề (1 đề = 1 bản ghi) + lấy ảnh crop để convert base64.
    ai_mongo_uri: str = "mongodb://localhost:27017"
    ai_mongo_db: str = "exam_parser"
    ai_mongo_collection: str = "exams"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "admin"
    minio_secret_key: str = "admin12345"
    minio_bucket: str = "exam-parser"
    minio_secure: bool = False

    # --- Upload ---
    max_upload_mb: int = 50
    allowed_ext: str = ".pdf,.png,.jpg,.jpeg"

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 9000
    cors_origins: str = "*"

    # --- Logging ---
    log_level: str = "INFO"

    @property
    def allowed_ext_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_ext.split(",") if e.strip()}

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
