# exam_parser_be — Backend Service

BE đứng giữa **client** và **AI service** (`exam_parser_paddle`):

```
client ──upload file──▶  BE (:9000)  ──POST /exams/parse──▶  AI service (:8000)
                          │                                    └─ lưu MinIO + Mongo (của AI)
                          └─ lưu lịch sử job vào Mongo của BE (be_jobs)
```

BE **không** xử lý OCR. Mọi việc bóc tách đẩy sang AI service qua **1 interface `AIClient`**
cấu hình bằng `AI_SERVICE_URL`. Đổi phương pháp AI khác = đổi URL (hoặc viết `AIClient` impl
mới), **không sửa router/nghiệp vụ**.

---

## 1. API

| Method | Path | Mô tả |
|---|---|---|
| POST | `/api/v1/documents` | Upload đề thi (`multipart`, field `file`) → chuyển tiếp AI → trả `job_id` + `exam_id` |
| GET | `/api/v1/documents/{job_id}` | Xem 1 job upload |
| GET | `/api/v1/documents?limit=&skip=` | List job upload (audit log) |
| GET | `/api/v1/exams` | **List lịch sử đề** (lọc `exam_id`/`source_file`, phân trang) |
| GET | `/api/v1/exams/{exam_id}` | **Chi tiết 1 đề** (output đầy đủ + ảnh nhúng base64) |
| GET | `/api/v1/health` | Trạng thái BE + ping AI service + Mongo |

### `GET /api/v1/exams` — list lịch sử đề (cho FE)
Đọc **read-only** từ store của AI service (Mongo `exam_parser.exams`). Query params:
`exam_id` (chứa), `source_file` (chứa), `page` (≥1), `page_size` (1–100).
```json
{
  "total": 12, "page": 1, "page_size": 20,
  "items": [
    {"exam_id":"a1b2c3d4","source_file":"de.pdf","status":"done","created_at":"2026-06-07T...",
     "n_pages":3,"n_questions":40,"n_groups":2,"n_mcq":38,"n_essay":2,
     "bucket":"exam-parser","minio_prefix":"exams/a1b2c3d4/"}
  ]
}
```

### `GET /api/v1/exams/{exam_id}` — chi tiết (cho trang verify)
BE đọc record đầy đủ, **tự tải ảnh crop từ MinIO theo `minio_key` và nhúng base64**
(`data_uri`) vào từng ảnh trong `output` → FE render thẳng, không cần presigned URL.
```json
{
  "exam_id":"a1b2c3d4","source_file":"de.pdf","status":"done","created_at":"...",
  "n_pages":3,"n_questions":40,"n_groups":2,
  "metadata":{"ma_de":"123","mon":"Toán", ...},
  "output":{
    "questions":[
      {"number":1,"type":"trac_nghiem_1_dap_an",
       "full_image":{"minio_key":"exams/a1b2c3d4/crops/q1_full.png","data_uri":"data:image/png;base64,..."},
       "content_image":{"data_uri":"data:image/png;base64,..."},
       "answers":[{"label":"A","image":{"data_uri":"data:image/png;base64,..."}}, ...]}
    ],
    "groups":[ ... ], "overlay":[ ... ]
  },
  "images_embedded": 187
}
```

> ⚠️ Cần kết nối tới **store của AI service**: biến `AI_MONGO_URI` + `MINIO_*` (xem §5).
> Compose đã trỏ sẵn qua `host.docker.internal` (AI service chạy stack khác trên cùng máy).

**POST /documents — thành công:** response gọn, chỉ trạng thái + id. Client (FE/mobile)
dùng `exam_id` gọi tiếp `GET /api/v1/exams/{exam_id}` để lấy chi tiết đề.
```json
{
  "job_id": "9f8e...hex",
  "status": "done",
  "exam_id": "a1b2c3d4",
  "error_code": null,
  "stage": null,
  "message": "Đã xử lý xong và lưu lên MinIO/Mongo"
}
```

**POST /documents — AI báo lỗi (HTTP 200, status=failed, giữ mã lỗi của AI):**
```json
{
  "job_id": "9f8e...hex",
  "status": "failed",
  "exam_id": "a1b2c3d4",
  "error_code": "E102",
  "stage": "mineru",
  "message": "Lỗi MinerU (layout/OCR)"
}
```

> Lỗi validate của BE (sai định dạng/ rỗng/ quá lớn) trả HTTP 415/422/413.
> AI service không gọi được → `error_code = BE502`.

Swagger UI: http://localhost:9000/docs

---

## 2. Chạy bằng Docker (khuyến nghị)

BE có **docker-compose riêng** (`be` + `be-mongo`), độc lập với stack AI service.

### Yêu cầu trước
AI service (`exam_parser_paddle`) phải đang chạy ở `:8000` (xem `exam_parser_paddle/README_DOCKER.md`).

### Lệnh
```bash
cd exam_parser_be
cp .env.example .env          # sửa AI_SERVICE_URL nếu cần

docker compose build
docker compose up -d
docker compose logs -f be
```

Kiểm tra:
```bash
curl http://localhost:9000/api/v1/health
# {"status":"ok","ai_service_url":"http://host.docker.internal:8000",
#  "ai_service_healthy":true,"mongo_healthy":true}
```

Gửi 1 file:
```bash
curl -X POST http://localhost:9000/api/v1/documents \
     -F "file=@/đường/dẫn/de.pdf"
```

### Kết nối tới AI service
- **Cùng máy (mặc định):** compose set `AI_SERVICE_URL=http://host.docker.internal:8000` và
  có `extra_hosts: host.docker.internal:host-gateway` → chạy được cả trên **WSL native Docker**
  (vốn không tự có host này).
- **Khác máy:** đặt trong `.env`:
  ```
  AI_SERVICE_URL=http://<IP-hoặc-domain-AI>:8000
  ```
- **Muốn 2 stack chung 1 network Docker** (gọi qua tên service thay vì host-gateway):
  ```bash
  docker network create shared-net
  ```
  Rồi thêm vào **cả 2** compose:
  ```yaml
  networks:
    shared-net:
      external: true
  # và gắn networks: [shared-net] cho service "be" và "ai-service"
  ```
  Khi đó đặt `AI_SERVICE_URL=http://exam_parser_ai:8000` (tên container AI service).

### Dừng / xoá
```bash
docker compose down            # giữ data
docker compose down -v         # xoá luôn volume be_mongo_data
```

---

## 3. Chạy local (không Docker)

```bash
cd exam_parser_be
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # AI_SERVICE_URL=http://localhost:8000, MONGO_URI trỏ Mongo đang chạy

uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
```

Cần 1 MongoDB cho BE (có thể chỉ chạy mình `be-mongo`):
```bash
docker compose up -d be-mongo  # Mongo BE ở cổng 27018
```

---

## 4. Cấu trúc code

```
app/
  main.py                 # FastAPI app + CORS + /health + mount router
  core/config.py          # Settings (.env) — AI_SERVICE_URL là điểm thay thế AI
  core/logging.py
  clients/ai_client.py    # AIClient (interface) + HttpAIClient + get_ai_client()  ← đổi AI ở đây
  schemas/job.py          # Job, JobStatus, UploadResponse, ...
  repositories/job_repo.py# CRUD Mongo be_jobs
  services/job_service.py # create / finalize / get / list
  routers/documents.py    # POST /documents, GET /documents[/{id}]
```

**Đổi AI service khác:** viết 1 class implement `AIClient` (vd `GrpcAIClient`) trong
`app/clients/ai_client.py`, rồi sửa `get_ai_client()` trả về impl mới. Router/service không đổi.

---

## 5. Biến môi trường chính

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `AI_SERVICE_URL` | `http://localhost:8000` | URL AI service (điểm thay thế) |
| `AI_TIMEOUT` | `300` | Timeout giây khi gọi AI (pipeline CPU lâu) |
| `MONGO_URI` | `...localhost:27018` | Mongo lịch sử job BE |
| `MONGO_DB` / `MONGO_COLLECTION` | `exam_parser_be` / `be_jobs` | |
| `AI_MONGO_URI` | `...localhost:27017` | **Mongo của AI service** (đọc lịch sử đề) |
| `AI_MONGO_DB` / `AI_MONGO_COLLECTION` | `exam_parser` / `exams` | |
| `MINIO_ENDPOINT` | `localhost:9000` | **MinIO của AI service** (lấy ảnh → base64) |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | `admin` / `admin12345` | |
| `MINIO_BUCKET` | `exam-parser` | |
| `MAX_UPLOAD_MB` | `50` | Giới hạn dung lượng upload |
| `ALLOWED_EXT` | `.pdf,.png,.jpg,.jpeg` | Đuôi file cho phép |
| `API_PORT` | `9000` | Cổng BE |

---

## 6. Ghi chú nâng cấp (chưa làm)

- **Bất đồng bộ:** hiện POST /documents chờ AI xong mới trả. Để nâng cấp: trả `job_id` ngay
  (`status=processing`), chạy `ai.parse` trong background task/worker, client poll
  `GET /documents/{job_id}`. Hàm `JobService.create/finalize` đã tách sẵn cho việc này.
- **Đọc kết quả chi tiết:** ảnh/`exam.json` nằm trên MinIO + Mongo của AI service. Nếu cần BE
  trả cấu trúc câu hỏi, thêm endpoint đọc Mongo của AI (read-only) hoặc proxy
  `GET /api/v1/exams/{id}` (cần mở rộng AI service).
