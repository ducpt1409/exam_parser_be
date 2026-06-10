# exam_parser_be — Backend Service

BE đứng giữa **client** và **AI service** (`exam_parser_mineru` hoặc `exam_parser_paddle`).
**POC: BE STATELESS** — không có Mongo riêng, dùng chung 1 store `exam_parser` với AI service:

```
client ──upload file──▶  BE (:9000)  ──POST /exams/parse──▶  AI service (:8001)
   │                      │                                    └─ lưu MinIO + Mongo
   │                      │                                       (store exam_parser)
   └──xem lịch sử/chi tiết─▶ BE đọc read-only store exam_parser ◀──┘
```

- Upload: BE chỉ forward file sang AI → AI xử lý + tự lưu → BE trả `exam_id`.
- Lịch sử = chính các bản ghi trong store `exam_parser` (`GET /exams`).
- Chi tiết 1 đề: `GET /exams/{exam_id}` (BE đọc Mongo + nhúng ảnh base64 từ MinIO).

BE **không** xử lý OCR. Mọi việc bóc tách đẩy sang AI service qua **1 interface `AIClient`**
cấu hình bằng `AI_SERVICE_URL`. Đổi phương pháp AI khác = đổi URL (hoặc viết `AIClient` impl
mới), **không sửa router/nghiệp vụ**.

---

## 1. API

| Method | Path | Mô tả |
|---|---|---|
| POST | `/api/v1/documents` | Upload đề thi (`multipart`, field `file`) → chuyển tiếp AI → trả `exam_id` |
| GET | `/api/v1/exams` | **List lịch sử đề** (lọc `exam_id`/`source_file`, phân trang) |
| GET | `/api/v1/exams/{exam_id}` | **Chi tiết 1 đề** (output đầy đủ + ảnh nhúng base64) |
| GET | `/api/v1/health` | Trạng thái BE + ping AI service + store exam_parser |

**POST /documents — thành công:** response gọn, chỉ trạng thái + id. Client (FE/mobile)
dùng `exam_id` gọi tiếp `GET /api/v1/exams/{exam_id}` để lấy chi tiết đề.
```json
{
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
  "status": "failed",
  "exam_id": "a1b2c3d4",
  "error_code": "E102",
  "stage": "mineru",
  "message": "Lỗi MinerU (layout/OCR)"
}
```

> Lỗi validate của BE (sai định dạng/ rỗng/ quá lớn) trả HTTP 415/422/413.
> AI service không gọi được → `error_code = BE502`.

### `GET /api/v1/exams` — list lịch sử đề (cho FE)
Đọc **read-only** từ store `exam_parser` (Mongo `exam_parser.exams` do AI service ghi).
Query params: `exam_id` (chứa), `source_file` (chứa), `page` (≥1), `page_size` (1–100).
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

Swagger UI: http://localhost:9000/docs

---

## 2. Chạy bằng Docker (khuyến nghị)

BE có **docker-compose riêng** (chỉ 1 service `be`), độc lập với stack AI service.

### Yêu cầu trước
AI service (`exam_parser_mineru`) phải đang chạy ở `:8001` + stack hạ tầng
(`exam_parser_infra`: MinIO :9000, Mongo :27017).

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
# {"status":"ok","ai_service_url":"http://host.docker.internal:8001",
#  "ai_service_healthy":true,"mongo_healthy":true}
```

Gửi 1 file:
```bash
curl -X POST http://localhost:9000/api/v1/documents \
     -F "file=@/đường/dẫn/de.pdf"
```

### Kết nối tới AI service
- **Cùng máy (mặc định):** compose set `AI_SERVICE_URL=http://host.docker.internal:8001` và
  có `extra_hosts: host.docker.internal:host-gateway` → chạy được cả trên **WSL native Docker**
  (vốn không tự có host này).
- **Khác máy:** đặt trong `.env`:
  ```
  AI_SERVICE_URL=http://<IP-hoặc-domain-AI>:8001
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
  Khi đó đặt `AI_SERVICE_URL=http://exam_parser_mineru_ai:8000` (tên container AI service).

### Dừng / xoá
```bash
docker compose down
```

---

## 3. Chạy local (không Docker)

```bash
cd exam_parser_be
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # AI_SERVICE_URL=http://localhost:8001

uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
```

BE không cần Mongo riêng — chỉ cần stack AI service (Mongo :27017 + MinIO :9000) đang chạy.

---

## 4. Cấu trúc code

```
app/
  main.py                  # FastAPI app + CORS + /health + mount router
  core/config.py           # Settings (.env) — AI_SERVICE_URL là điểm thay thế AI
  core/logging.py
  clients/ai_client.py     # AIClient (interface) + HttpAIClient + get_ai_client()  ← đổi AI ở đây
  clients/minio_client.py  # MinioStorage — tải ảnh crop từ MinIO → base64
  schemas/common.py        # UploadResponse, HealthResponse
  schemas/exam.py          # ExamSummary, ExamListResponse, ExamDetailResponse
  repositories/exam_repo.py# Read-only Mongo store exam_parser (AI service ghi)
  services/exam_service.py # list + get_detail (nhúng base64)
  routers/documents.py     # POST /documents (stateless, forward AI)
  routers/exams.py         # GET /exams, GET /exams/{exam_id}
```

**Đổi AI service khác:** viết 1 class implement `AIClient` (vd `GrpcAIClient`) trong
`app/clients/ai_client.py`, rồi sửa `get_ai_client()` trả về impl mới. Router/service không đổi.

---

## 5. Biến môi trường chính

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `AI_SERVICE_URL` | `http://localhost:8001` | URL AI service (điểm thay thế) |
| `AI_TIMEOUT` | `600` | Timeout giây khi gọi AI (request đầu nạp model lâu) |
| `AI_MONGO_URI` | `...localhost:27017` | **Mongo store exam_parser** (AI ghi, BE đọc) |
| `AI_MONGO_DB` / `AI_MONGO_COLLECTION` | `exam_parser` / `exams` | |
| `MINIO_ENDPOINT` | `localhost:9000` | **MinIO của AI service** (lấy ảnh → base64) |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | `admin` / `admin12345` | |
| `MINIO_BUCKET` | `exam-parser` | |
| `MAX_UPLOAD_MB` | `50` | Giới hạn dung lượng upload |
| `ALLOWED_EXT` | `.pdf,.png,.jpg,.jpeg` | Đuôi file cho phép |
| `API_PORT` | `9000` | Cổng BE |

---

## 6. Ghi chú nâng cấp (chưa làm)

- **Bất đồng bộ:** hiện POST /documents chờ AI xong mới trả. Để nâng cấp: cần job store
  (đưa lại Mongo riêng hoặc thêm collection job vào store exam_parser), trả `job_id` ngay
  (`status=processing`), chạy `ai.parse` trong background task/worker, client poll.
- **Audit log upload:** POC bỏ lưu job phía BE. Khi cần audit (ai upload, lúc nào, lỗi gì
  kể cả khi AI chết), khôi phục `JobService`/`be_jobs` từ lịch sử git (bản 1.2.0).
