"""Nghiệp vụ lịch sử đề: list (lọc + phân trang) + detail (nhúng base64 ảnh).

Detail: đọc full record từ Mongo của AI → duyệt cấu trúc `output`, với MỌI ảnh có
`minio_key` thì tải bytes từ MinIO, encode base64 và gắn thêm field `data_uri` để FE
render thẳng (không phụ thuộc presigned URL nội bộ).
"""
from __future__ import annotations

import io
import zipfile
from typing import Any, Optional

from app.clients.minio_client import MinioStorage
from app.core.logging import logger
from app.repositories.exam_repo import ExamRepository
from app.schemas.exam import ExamDetailResponse, ExamListResponse, ExamSummary


class ExamDeleteError(Exception):
    """Lỗi xoá đề ở 1 bước cụ thể — router map ra response {stage, error_code, ...}.

    Mã lỗi: BE404 lookup | BE510 minio_list | BE511 minio_delete | BE512 mongo_delete.
    """

    def __init__(self, stage: str, error_code: str, message: str, detail: str = ""):
        super().__init__(message)
        self.stage = stage
        self.error_code = error_code
        self.message = message
        self.detail = detail


class ExamService:
    def __init__(self, repo: ExamRepository, storage: MinioStorage):
        self.repo = repo
        self.storage = storage

    # ------------------------------------------------------------
    def list(
        self,
        exam_id: Optional[str] = None,
        source_file: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ExamListResponse:
        total, docs = self.repo.list(
            exam_id=exam_id, source_file=source_file, page=page, page_size=page_size
        )
        return ExamListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=[ExamSummary.from_doc(d) for d in docs],
        )

    # ------------------------------------------------------------
    def get_detail(self, exam_id: str) -> Optional[ExamDetailResponse]:
        doc = self.repo.get(exam_id)
        if not doc:
            return None

        output = doc.get("output", {}) or {}
        n_embedded = self._embed_images(output)

        return ExamDetailResponse(
            exam_id=str(doc.get("_id") or doc.get("exam_id", "")),
            source_file=doc.get("source_file", ""),
            status=doc.get("status", "done"),
            created_at=doc.get("created_at", ""),
            n_pages=doc.get("n_pages", 0),
            n_questions=doc.get("n_questions", 0),
            n_groups=doc.get("n_groups", 0),
            metadata=doc.get("metadata", {}) or output.get("metadata", {}),
            output=output,
            images_embedded=n_embedded,
        )

    # ------------------------------------------------------------
    def build_zip(self, exam_id: str) -> Optional[tuple[str, io.BytesIO]]:
        """Nén toàn bộ thư mục MinIO của 1 đề (crops + overlay + raw + exam.json) thành zip.

        Trả (tên file zip, buffer). Đề không tồn tại hoặc không có file nào → None.
        """
        doc = self.repo.get(exam_id)
        if not doc:
            return None

        prefix = doc.get("minio_prefix") or f"exams/{exam_id}/"
        keys = self.storage.list_keys(prefix)
        if not keys:
            logger.warning(f"[ExamService] đề {exam_id}: không có object nào dưới {prefix}")
            return None

        buf = io.BytesIO()
        n_ok = 0
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for key in keys:
                data = self.storage.get_bytes(key)
                if data is None:
                    continue    # 1 file lỗi không làm hỏng cả zip
                # Tên trong zip = đường dẫn tương đối dưới prefix (crops/q1_full.png, ...)
                arcname = key[len(prefix):] if key.startswith(prefix) else key
                zf.writestr(arcname, data)
                n_ok += 1
        if n_ok == 0:
            return None
        buf.seek(0)
        logger.info(f"[ExamService] zip đề {exam_id}: {n_ok}/{len(keys)} file")
        return f"exam_{exam_id}.zip", buf

    # ------------------------------------------------------------
    def delete(self, exam_id: str) -> dict[str, Any]:
        """Xoá 1 đề theo từng bước, lỗi bước nào raise ExamDeleteError dừng ở bước đó.

        Bước: [1] lookup Mongo → [2] list object MinIO → [3] xoá object MinIO →
        [4] xoá bản ghi Mongo. Xoá MinIO TRƯỚC, Mongo SAU — nếu xoá file dở dang
        thì bản ghi vẫn còn trong lịch sử để bấm xoá lại (không mồ côi file rác).
        """
        # [1] lookup
        try:
            doc = self.repo.get(exam_id)
        except Exception as e:
            raise ExamDeleteError(
                "lookup", "BE510", "Không đọc được bản ghi từ Mongo", str(e)) from e
        if not doc:
            raise ExamDeleteError(
                "lookup", "BE404", f"Không tìm thấy đề {exam_id}",
                "Đề không tồn tại hoặc đã bị xoá trước đó")

        prefix = doc.get("minio_prefix") or f"exams/{exam_id}/"

        # [2] list object MinIO
        try:
            keys = self.storage.list_keys(prefix, strict=True)
        except Exception as e:
            raise ExamDeleteError(
                "minio_list", "BE510",
                "Không liệt kê được file trên MinIO (chưa xoá gì)", str(e)) from e

        # [3] xoá object MinIO
        files_deleted, failed = self.storage.remove_keys(keys) if keys else (0, [])
        if failed:
            preview = ", ".join(failed[:5]) + ("…" if len(failed) > 5 else "")
            raise ExamDeleteError(
                "minio_delete", "BE511",
                f"Xoá MinIO dở dang: {files_deleted}/{len(keys)} file "
                f"({len(failed)} lỗi) — bản ghi Mongo GIỮ NGUYÊN, hãy xoá lại",
                f"Key lỗi: {preview}")

        # [4] xoá bản ghi Mongo
        try:
            self.repo.delete(exam_id)
        except Exception as e:
            raise ExamDeleteError(
                "mongo_delete", "BE512",
                f"Đã xoá {files_deleted} file MinIO nhưng xoá bản ghi Mongo lỗi — "
                f"hãy xoá lại để dọn bản ghi", str(e)) from e

        logger.info(f"[ExamService] xoá đề {exam_id}: {files_deleted} file MinIO + bản ghi Mongo")
        return {"files_deleted": files_deleted}

    # ------------------------------------------------------------
    def _embed_images(self, node: Any, _cache: Optional[dict] = None) -> int:
        """Duyệt đệ quy cấu trúc; gắn data_uri cho mọi dict có minio_key.

        Trả về số ảnh đã nhúng. Cache theo key để không tải trùng (vd passage = header).
        """
        if _cache is None:
            _cache = {}
        count = 0

        if isinstance(node, dict):
            key = node.get("minio_key")
            # Là 1 đối tượng ảnh khi có minio_key trỏ tới file ảnh
            if isinstance(key, str) and key and self._looks_like_image(key):
                if key not in _cache:
                    _cache[key] = self.storage.get_data_uri(key, "image/png")
                data_uri = _cache[key]
                if data_uri:
                    node["data_uri"] = data_uri
                    count += 1
            # Tiếp tục duyệt các giá trị con
            for v in node.values():
                count += self._embed_images(v, _cache)

        elif isinstance(node, list):
            for item in node:
                count += self._embed_images(item, _cache)

        return count

    @staticmethod
    def _looks_like_image(key: str) -> bool:
        k = key.lower()
        return k.endswith((".png", ".jpg", ".jpeg", ".webp"))


def get_exam_service() -> ExamService:
    # Lười khởi tạo để không cần Mongo/MinIO lúc import
    from app.clients.minio_client import get_storage
    from app.repositories.exam_repo import get_exam_repo
    return ExamService(get_exam_repo(), get_storage())
