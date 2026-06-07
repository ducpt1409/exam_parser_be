# Changelog — exam_parser_be

## [1.1.0] - 2026-06-07 - 2 API lịch sử đề cho FE (list + detail base64)

### Mục đích
FE cần xem lịch sử đề + verify kết quả. Thêm 2 API đọc store của AI service.

### Giải pháp
- **`app/core/config.py`**: thêm `ai_mongo_*` (đọc lịch sử đề) + `minio_*` (lấy ảnh crop).
- **`app/repositories/exam_repo.py`** (MỚI): read-only Mongo `exam_parser.exams` — `list()`
  (lọc `exam_id`/`source_file` bằng regex + phân trang, bỏ `output`), `get()`.
- **`app/clients/minio_client.py`** (MỚI): `MinioStorage.get_data_uri()` — tải bytes theo
  `minio_key` → base64 data URI (không dùng presigned URL nội bộ).
- **`app/services/exam_service.py`** (MỚI): `list()` (basic) + `get_detail()` (duyệt đệ quy
  `output`, nhúng `data_uri` cho mọi ảnh có `minio_key`, cache tránh tải trùng).
- **`app/schemas/exam.py`** (MỚI): `ExamSummary`, `ExamListResponse`, `ExamDetailResponse`.
- **`app/routers/exams.py`** (MỚI): `GET /api/v1/exams`, `GET /api/v1/exams/{exam_id}`.
- **`app/main.py`**: mount router exams.
- **requirements** thêm `minio`; **compose** + **.env.example** thêm `AI_MONGO_*`/`MINIO_*`
  (trỏ host.docker.internal tới stack AI service); **README** mô tả 2 API.

---

## [1.0.0] - 2026-06-07 - Khởi tạo BE proxy sang AI service

### Mục đích
BE đứng giữa client và AI service (`exam_parser_paddle`): nhận file đề thi, chuyển tiếp sang
AI service, lưu lịch sử job, trả trạng thái. Thiết kế để đổi AI service dễ (chỉ trỏ URL).

### Giải pháp
- **`app/core/config.py`**: Settings (.env). `AI_SERVICE_URL` là điểm thay thế AI duy nhất.
- **`app/clients/ai_client.py`**: `AIClient` (interface) + `HttpAIClient` (gọi
  `POST /api/v1/exams/parse`), chuẩn hoá kết quả thành `AIParseResult` (giữ `error_code`/`stage`
  từ AI). `get_ai_client()` factory cho DI.
- **`app/schemas/job.py`**: `Job`, `JobStatus`, `UploadResponse`, `JobListResponse`, `HealthResponse`.
- **`app/repositories/job_repo.py`**: CRUD Mongo collection `be_jobs` (upsert/get/list/ping).
- **`app/services/job_service.py`**: `create()` (processing) / `finalize()` (theo kết quả AI) /
  `get()` / `list()`.
- **`app/routers/documents.py`**: `POST /api/v1/documents` (đồng bộ: upload → AI → lưu job),
  `GET /documents/{id}`, `GET /documents`.
- **`app/main.py`**: CORS + `/api/v1/health` (ping AI + Mongo) + mount router.
- **Docker RIÊNG**: `Dockerfile`, `docker-compose.yml` (`be` :9000 + `be-mongo` :27018,
  `extra_hosts host-gateway` cho WSL), `.dockerignore`, `.env.example`.
- **`README.md`**: cách chạy (Docker / local), nối mạng tới AI service, đổi AI.

### Còn lại
- Chế độ bất đồng bộ (background task) — đã tách hàm sẵn, chưa bật.
- Endpoint đọc kết quả chi tiết (ảnh/exam.json từ MinIO/Mongo của AI).
