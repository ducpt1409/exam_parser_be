"""Repository read-only tới lịch sử đề của AI service (Mongo `exam_parser.exams`).

BE KHÔNG ghi vào store này — chỉ đọc để list lịch sử + lấy chi tiết. Đây là store do
AI service (exam_parser_paddle) tạo: mỗi đề = 1 document, `_id` = exam_id, có field
`output` = toàn bộ cấu trúc Exam (ảnh tham chiếu MinIO qua `minio_key`).
"""
from __future__ import annotations

import re
from typing import Any, Optional

from pymongo import DESCENDING, MongoClient

from app.core.config import settings
from app.core.logging import logger

# Field tóm tắt cho list (bỏ `output` cho nhẹ)
SUMMARY_PROJECTION = {"output": 0}


class ExamRepository:
    def __init__(
        self,
        uri: Optional[str] = None,
        db: Optional[str] = None,
        collection: Optional[str] = None,
    ):
        self.uri = uri or settings.ai_mongo_uri
        self.db_name = db or settings.ai_mongo_db
        self.coll_name = collection or settings.ai_mongo_collection
        self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
        self.collection = self.client[self.db_name][self.coll_name]

    # ------------------------------------------------------------
    def _build_query(
        self, exam_id: Optional[str], source_file: Optional[str]
    ) -> dict[str, Any]:
        q: dict[str, Any] = {}
        if exam_id:
            q["_id"] = {"$regex": re.escape(exam_id), "$options": "i"}
        if source_file:
            q["source_file"] = {"$regex": re.escape(source_file), "$options": "i"}
        return q

    def list(
        self,
        exam_id: Optional[str] = None,
        source_file: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[int, list[dict[str, Any]]]:
        """List bản ghi (mới nhất trước) + tổng số, đã lọc + phân trang."""
        query = self._build_query(exam_id, source_file)
        total = self.collection.count_documents(query)
        skip = max(0, (page - 1) * page_size)
        cursor = (
            self.collection.find(query, SUMMARY_PROJECTION)
            .sort("created_at", DESCENDING)
            .skip(skip)
            .limit(page_size)
        )
        return total, list(cursor)

    def get(self, exam_id: str) -> Optional[dict[str, Any]]:
        """Đọc đầy đủ 1 bản ghi (gồm `output`)."""
        return self.collection.find_one({"_id": exam_id})

    def ping(self) -> bool:
        try:
            self.client.admin.command("ping")
            return True
        except Exception as e:
            logger.error(f"[ExamRepo] AI Mongo ping lỗi — {e}")
            return False


_repo: Optional[ExamRepository] = None


def get_exam_repo() -> ExamRepository:
    global _repo
    if _repo is None:
        _repo = ExamRepository()
    return _repo
