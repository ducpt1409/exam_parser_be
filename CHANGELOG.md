# Changelog — exam_parser_be

## [1.5.0] - 2026-06-12 - API tải dữ liệu đề thi (zip thư mục MinIO)

### Mục đích
FE thêm nút "Tải dữ liệu đề thi" (bảng lịch sử + trang chi tiết) → BE cần API gom toàn bộ
thư mục MinIO của 1 đề (crops + overlay + raw PDF + exam.json) thành 1 file zip.

### Giải pháp
- **`app/clients/minio_client.py`**: thêm `list_keys(prefix)` — list object đệ quy.
- **`app/services/exam_service.py`**: thêm `build_zip(exam_id)` — đọc `minio_prefix` từ
  record, tải từng object, nén zip in-memory (1 file lỗi không hỏng cả zip).
- **`app/routers/exams.py`**: `GET /api/v1/exams/{exam_id}/download` → StreamingResponse
  `application/zip` (`exam_{id}.zip`), chạy `asyncio.to_thread` để không chặn event loop.
  404 nếu đề không tồn tại / không có dữ liệu trên MinIO.

---

## [1.4.0] - 2026-06-10 - BE stateless: bỏ Mongo riêng, dùng chung store exam_parser

### Mục đích
POC: BE không cần lưu gì — chỉ upload cho AI service xử lý, AI lưu vào store
`exam_parser` (Mongo + MinIO), BE truy vấn store đó. Lịch sử = chính các bản ghi
exam_parser (`GET /exams`), không còn job riêng.

### Giải pháp
- **XÓA** `app/schemas/job.py`, `app/repositories/job_repo.py`, `app/services/job_service.py`
  (khôi phục từ git nếu sau cần audit log / chế độ bất đồng bộ).
- **`app/schemas/common.py`** (MỚI): `UploadResponse` (bỏ `job_id`) + `HealthResponse`.
- **`app/routers/documents.py`**: `POST /documents` stateless — validate → forward AI →
  trả `{status, exam_id, error_code, stage, message}`. Bỏ `GET /documents`,
  `GET /documents/{job_id}`.
- **`app/main.py`**: `/health` ping Mongo store exam_parser (qua `exam_repo`) thay vì
  Mongo riêng của BE.
- **`app/core/config.py`**: bỏ `mongo_uri/mongo_db/mongo_collection` (BE) — chỉ còn
  `AI_MONGO_*` (store exam_parser) + `MINIO_*`.
- **`docker-compose.yml`**: bỏ service `be-mongo` + volume `be_mongo_data` + env Mongo BE
  → stack BE chỉ còn 1 container `be`.
- **`.env.example`**, **README**: cập nhật theo.

---

## [1.3.0] - 2026-06-10 - Upload chỉ trả id, chi tiết lấy qua API riêng

### Mục đích
Quy trình mới: upload xong chỉ nhận `{job_id, status, exam_id, error_code, stage, message}`;
client (FE/mobile) dùng `exam_id` gọi tiếp `GET /api/v1/exams/{exam_id}` lấy chi tiết đề.
Khớp với AI service mineru 0.2.3 (`POST /exams/parse` chỉ trả `{status, exam_id, message}`).

### Giải pháp
- **`app/clients/ai_client.py`**: bỏ tham số `include_images`; `AIParseResult` bỏ
  `n_pages/n_questions/n_groups/bucket/minio_prefix/result` — chỉ còn
  `ok, exam_id, message, stage, error_code, detail`.
- **`app/schemas/job.py`**: `Job` bỏ các field thống kê (n_*, bucket, minio_prefix) —
  không lưu lặp, chi tiết đã có trong store của AI; `UploadResponse` bỏ `result` +
  `minio_prefix`.
- **`app/routers/documents.py`**: `POST /documents` bỏ query `include_images`, response gọn.
- 2 API lịch sử (`GET /exams`, `GET /exams/{exam_id}`) **không đổi** — vẫn đọc đầy đủ
  từ Mongo/MinIO của AI service.

---

## [1.2.0] - 2026-06-08 - Upload trả luôn kết quả đầy đủ (public API)

### Mục đích
API upload khi thành công trả LUÔN `result` (kết quả đầy đủ từ AI: output + ảnh base64),
phục vụ public API thu thập + đánh giá.

### Giải pháp
- **`app/clients/ai_client.py`**: `AIParseResult` thêm `result`; `parse()` thêm tham số
  `include_images` (forward query `?include_images=`), gắn toàn bộ payload AI vào `result`.
- **`app/schemas/job.py`**: `UploadResponse` thêm `result` (chỉ khi done).
- **`app/routers/documents.py`**: `POST /documents` thêm query `include_images`; trả `result`
  từ AI. KHÔNG lưu base64 vào `be_jobs` (job vẫn gọn).

---

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
