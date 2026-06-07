# exam_parser_be — Hướng dẫn xây dựng Backend (cho Antigravity)

> Đọc kỹ toàn bộ trước khi code. Đây là service **BE riêng**, tách hoàn toàn khỏi AI service
> (`exam_parser_paddle`). BE **không** tự bóc tách đề — nó nhận file từ client, **chuyển tiếp**
> sang AI service, nhận kết quả rồi trả về client. Mục tiêu: sau này đổi phương pháp AI khác
> thì **chỉ cần trỏ BE sang AI service mới**, không sửa client.

---

## 0. Nguyên tắc bất di bất dịch

1. **BE là lớp proxy + nghiệp vụ**, KHÔNG nhúng logic OCR/PaddleOCR. Mọi xử lý tài liệu đẩy
   sang AI service qua HTTP.
2. **AI service có thể thay thế.** Mọi chỗ gọi AI phải đi qua **1 interface duy nhất**
   (`AIClient`) cấu hình bằng biến môi trường `AI_SERVICE_URL`. Đổi AI = đổi URL (hoặc viết
    1 implementation `AIClient` mới), không đụng tới router/nghiệp vụ.
3. **Docker riêng.** BE có `docker-compose.yml` **của riêng nó** (KHÔNG dùng chung compose với
   AI service). Hai stack chạy độc lập, nói chuyện qua mạng.
4. Code + comment + thông báo lỗi: **tiếng Việt**.
5. Mọi thay đổi ghi `CHANGELOG.md` trong thư mục `exam_parser_be`.

---

## 1. AI service đã có sẵn (hợp đồng API để BE gọi)

AI service `exam_parser_paddle` expose đúng **1 endpoint xử lý** (chi tiết trong
`exam_parser_paddle/README_DOCKER.md`):

### `POST {AI_SERVICE_URL}/api/v1/exams/parse`
- `multipart/form-data`, field **`file`** = file đề thi (`.pdf/.png/.jpg/.jpeg`).
- **200 — thành công:**
  ```json
  {
    "status": "done",
    "exam_id": "a1b2c3d4",
    "message": "Đã xử lý xong và lưu lên MinIO/Mongo",
    "n_pages": 3, "n_questions": 40, "n_groups": 2,
    "bucket": "exam-parser", "minio_prefix": "exams/a1b2c3d4/"
  }
  ```
- **Lỗi — HTTP 4xx/5xx + body:**
  ```json
  {
    "status": "failed", "exam_id": "a1b2c3d4",
    "stage": "ocr", "error_code": "E102",
    "message": "Lỗi PaddleOCR (layout/OCR)", "detail": "..."
  }
  ```

### `GET {AI_SERVICE_URL}/api/v1/health`
```json
{"status":"ok","vlm_enabled":false,"minio_endpoint":"minio:9000","mongo_enabled":true}
```

**Bảng mã lỗi AI service** (BE map lại, đừng phụ thuộc `message`):

| Mã | stage | HTTP | Ý nghĩa |
|---|---|---|---|
| E400/E415/E422 | input | 400/415/422 | File sai/không hỗ trợ/rỗng |
| E101 | preprocess | 500 | Render PDF |
| E102 | ocr | 500 | PaddleOCR |
| E103 | anchor | 500 | Anchor |
| E104 | snake_walker | 500 | Gom câu/nhóm |
| E105 | classify | 500 | Phân loại |
| E106 | crop | 500 | Cắt ảnh/overlay |
| E107 | minio_upload | 502 | Upload MinIO |
| E108 | mongo_save | 502 | Lưu Mongo |
| E500 | unknown | 500 | Không xác định |

> Lưu ý: kết quả chi tiết (ảnh crop, overlay, exam.json) AI service đã lưu lên MinIO + Mongo.
> AI service KHÔNG trả JSON cấu trúc qua API parse. Nếu BE cần đọc cấu trúc/ảnh, đọc trực tiếp
> từ MinIO/Mongo (xem §6 — tuỳ phạm vi, có thể làm sau).

---

## 2. Phạm vi BE (làm gì)

Tối thiểu (POC):

1. **`POST /api/v1/documents`** — client upload file đề thi.
   - Validate cơ bản (đuôi file, dung lượng tối đa cấu hình được, vd 50MB).
   - Tạo 1 bản ghi job trong DB của BE (`status=processing`).
   - Gọi `AIClient.parse(file)` → AI service.
   - Nhận kết quả: cập nhật bản ghi (`status=done` + `exam_id` + `minio_prefix` + thống kê),
     hoặc (`status=failed` + `error_code` + `stage` + `detail`).
   - Trả client: `{ job_id, status, exam_id?, error_code?, stage? }`.

2. **`GET /api/v1/documents/{job_id}`** — xem trạng thái/kết quả 1 job.

3. **`GET /api/v1/documents`** — list job (phân trang).

4. **`GET /api/v1/health`** — gồm cả ping AI service (`/api/v1/health` của AI).

> Đồng bộ hay bất đồng bộ? Pipeline AI chạy CPU có thể lâu (vài chục giây/đề). Chọn **1** trong 2:
> - **Đồng bộ (đơn giản, hợp POC):** BE gọi AI và chờ, tăng timeout HTTP client (vd 300s).
> - **Bất đồng bộ (khuyến nghị nếu có thời gian):** BE trả `job_id` ngay (`status=processing`),
>   chạy gọi AI trong background task / worker, client poll `GET /documents/{job_id}`.
>
> Hãy làm **đồng bộ trước** cho chạy được, để sẵn chỗ nâng cấp bất đồng bộ (tách hàm xử lý).

---

## 3. Stack đề xuất

- **Python 3.11 + FastAPI + Uvicorn** (đồng bộ với AI service, dễ bảo trì). Nếu team mạnh
  Node thì NestJS cũng được — nhưng mặc định dùng FastAPI.
- **HTTP client:** `httpx` (async, hỗ trợ multipart, timeout).
- **DB lưu job BE:** dùng lại **MongoDB** cho nhẹ (collection riêng `be_jobs`), HOẶC PostgreSQL
  nếu cần quan hệ. Mặc định: MongoDB (1 container riêng của BE, KHÔNG dùng chung Mongo của AI).
- **Cấu hình:** `pydantic-settings`, đọc `.env`.

### Cây thư mục đề xuất
```
exam_parser_be/
  app/
    main.py                 # FastAPI app + CORS + mount router + /health
    core/
      config.py             # Settings (.env): AI_SERVICE_URL, AI_TIMEOUT, MONGO_URI, ...
      logging.py
    clients/
      ai_client.py          # AIClient interface + HttpAIClient (gọi exam_parser_paddle)
    services/
      job_service.py        # nghiệp vụ: tạo/cập nhật/đọc job
    repositories/
      job_repo.py           # CRUD Mongo collection be_jobs
    schemas/
      job.py                # JobCreate/JobOut + AIParseResult
    routers/
      documents.py          # POST /documents, GET /documents, GET /documents/{id}
  tests/
  requirements.txt
  Dockerfile
  docker-compose.yml        # RIÊNG của BE
  .dockerignore
  .env.example
  CHANGELOG.md
  README.md
```

---

## 4. `AIClient` — điểm thay thế AI service

Đây là phần quan trọng nhất cho mục tiêu "đổi AI dễ". Định nghĩa **interface** + 1 impl HTTP.

```python
# app/clients/ai_client.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import httpx
from app.core.config import settings


@dataclass
class AIParseResult:
    ok: bool
    exam_id: Optional[str] = None
    n_pages: int = 0
    n_questions: int = 0
    n_groups: int = 0
    bucket: str = ""
    minio_prefix: str = ""
    # khi lỗi:
    stage: Optional[str] = None
    error_code: Optional[str] = None
    message: str = ""
    detail: str = ""


class AIClient(ABC):
    """Hợp đồng AI service. Đổi phương pháp AI = viết impl mới, không sửa router."""
    @abstractmethod
    async def parse(self, filename: str, content: bytes, content_type: str) -> AIParseResult: ...
    @abstractmethod
    async def health(self) -> bool: ...


class HttpAIClient(AIClient):
    """Gọi exam_parser_paddle qua HTTP (POST /api/v1/exams/parse)."""
    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        self.base_url = (base_url or settings.ai_service_url).rstrip("/")
        self.timeout = timeout or settings.ai_timeout

    async def parse(self, filename, content, content_type) -> AIParseResult:
        url = f"{self.base_url}/api/v1/exams/parse"
        files = {"file": (filename, content, content_type)}
        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            try:
                r = await cli.post(url, files=files)
            except httpx.RequestError as e:
                # AI service không reachable → coi như lỗi hạ tầng
                return AIParseResult(ok=False, stage="ai_unreachable",
                                     error_code="BE502", message="Không gọi được AI service",
                                     detail=str(e))
            data = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
            if r.status_code == 200 and data.get("status") == "done":
                return AIParseResult(ok=True, exam_id=data.get("exam_id"),
                                     n_pages=data.get("n_pages",0), n_questions=data.get("n_questions",0),
                                     n_groups=data.get("n_groups",0), bucket=data.get("bucket",""),
                                     minio_prefix=data.get("minio_prefix",""))
            return AIParseResult(ok=False, exam_id=data.get("exam_id"),
                                 stage=data.get("stage"), error_code=data.get("error_code","BE500"),
                                 message=data.get("message","AI xử lý lỗi"), detail=data.get("detail",""))

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as cli:
                r = await cli.get(f"{self.base_url}/api/v1/health")
                return r.status_code == 200
        except httpx.RequestError:
            return False


def get_ai_client() -> AIClient:
    """Factory — chỗ duy nhất quyết định dùng impl nào (DI cho FastAPI)."""
    return HttpAIClient()
```

> Router/service **chỉ** phụ thuộc `AIClient` (qua `Depends(get_ai_client)`), không bao giờ
> import `httpx` trực tiếp. Đổi AI khác → viết `GrpcAIClient`/`OtherAIClient` + sửa factory.

---

## 5. Luồng `POST /api/v1/documents` (đồng bộ)

```python
# app/routers/documents.py (rút gọn)
@router.post("/documents")
async def upload_document(file: UploadFile = File(...),
                          ai: AIClient = Depends(get_ai_client)):
    # 1. Validate đuôi + dung lượng (đọc settings.max_upload_mb)
    # 2. job = job_service.create(filename, status="processing")
    content = await file.read()
    result = await ai.parse(file.filename, content, file.content_type or "application/pdf")
    # 3. cập nhật job theo result (done/failed) + lưu exam_id, minio_prefix, error_code...
    job = job_service.finalize(job_id, result)
    # 4. trả gọn cho client
    return {
        "job_id": job.id,
        "status": job.status,            # done | failed
        "exam_id": job.exam_id,
        "error_code": job.error_code,    # null nếu done
        "stage": job.stage,              # null nếu done
        "minio_prefix": job.minio_prefix,
    }
```

Bản ghi job (`be_jobs`) gợi ý field:
`{_id, filename, status, exam_id, n_pages, n_questions, n_groups, bucket, minio_prefix,
error_code, stage, detail, created_at, updated_at}`.

---

## 6. (Tuỳ chọn, làm sau) BE phục vụ kết quả chi tiết

AI service đã lưu `exam.json` + ảnh lên MinIO và document lên Mongo của AI. Nếu cần BE trả
cấu trúc/ảnh cho frontend, chọn 1 hướng (ghi rõ trong README, đừng làm cả 2):

- **A. BE đọc Mongo của AI** (read-only): thêm `AI_MONGO_URI` + repo đọc collection `exams`,
  endpoint `GET /documents/{job_id}/detail` trả `output`.
- **B. Mở rộng AI service** thêm `GET /api/v1/exams/{id}` rồi BE proxy tiếp.

> POC chưa cần. Chỉ ghi chú để không thiết kế chặn đường nâng cấp.

---

## 7. Docker (RIÊNG của BE — bắt buộc viết)

BE có compose **độc lập**. Hai cách kết nối tới AI service:

- **Khác máy/khác stack:** đặt `AI_SERVICE_URL=http://<host-AI>:8000` trong `.env`.
- **Cùng máy, muốn chung mạng:** tạo 1 **external network** dùng chung rồi cho cả 2 compose
  join (ghi rõ trong README cách `docker network create shared-net` và `networks: {shared-net: {external: true}}`).

### `Dockerfile` (gợi ý)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
ENV PYTHONPATH=/app
EXPOSE 9000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:9000/api/v1/health')" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
```

### `docker-compose.yml` (RIÊNG, gợi ý)
```yaml
services:
  be:
    build: .
    image: exam_parser_be:latest
    container_name: exam_parser_be
    restart: unless-stopped
    ports:
      - "9000:9000"     # cổng BE (khác 8000 của AI service)
    depends_on:
      be-mongo:
        condition: service_started
    environment:
      AI_SERVICE_URL: ${AI_SERVICE_URL:-http://host.docker.internal:8000}
      AI_TIMEOUT: "300"
      MONGO_URI: mongodb://${BE_MONGO_USER:-admin}:${BE_MONGO_PASS:-admin12345}@be-mongo:27017/?authSource=admin
      MONGO_DB: exam_parser_be
      MAX_UPLOAD_MB: "50"
      CORS_ORIGINS: "*"
    # WSL native Docker KHÔNG có host.docker.internal → thêm dòng dưới nếu cần:
    # extra_hosts: ["host.docker.internal:host-gateway"]

  be-mongo:
    image: mongo:7
    container_name: exam_parser_be_mongo
    restart: unless-stopped
    ports:
      - "27018:27017"   # tránh đụng cổng 27017 của Mongo AI service
    volumes:
      - be_mongo_data:/data/db
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${BE_MONGO_USER:-admin}
      MONGO_INITDB_ROOT_PASSWORD: ${BE_MONGO_PASS:-admin12345}

volumes:
  be_mongo_data:
```

> ⚠️ **Cổng phải khác AI service:** BE 9000, AI 8000; BE-Mongo map ra 27018 (AI-Mongo 27017);
> tránh trùng. Nếu chạy chung 1 máy, dùng external shared network để BE gọi AI qua tên service
> thay vì `host.docker.internal` (đặc biệt trên **WSL native Docker** vốn không có host này).

### Lệnh
```bash
cd exam_parser_be
cp .env.example .env          # điền AI_SERVICE_URL trỏ tới AI service đang chạy
docker compose build
docker compose up -d
curl http://localhost:9000/api/v1/health
```

---

## 8. `.env.example` (gợi ý)
```
AI_SERVICE_URL=http://localhost:8000
AI_TIMEOUT=300
MONGO_URI=mongodb://admin:admin12345@localhost:27018/?authSource=admin
MONGO_DB=exam_parser_be
MONGO_COLLECTION=be_jobs
MAX_UPLOAD_MB=50
CORS_ORIGINS=*
LOG_LEVEL=INFO
```

---

## 9. Checklist hoàn thành (Antigravity tự kiểm)

- [ ] `AIClient` interface + `HttpAIClient` (mọi call AI đi qua đây; router không import httpx).
- [ ] `POST /documents` chạy thông đồng bộ: upload → gọi AI → lưu job → trả `{job_id,status,...}`.
- [ ] Map đầy đủ kết quả `done`/`failed` (giữ `error_code` + `stage` từ AI service).
- [ ] `GET /documents/{job_id}`, `GET /documents`, `GET /health` (health ping cả AI service).
- [ ] Validate đuôi file + `MAX_UPLOAD_MB`.
- [ ] `Dockerfile` + `docker-compose.yml` RIÊNG của BE, cổng không đụng AI service, chạy được.
- [ ] `README.md` ghi cách trỏ `AI_SERVICE_URL` + cách nối mạng Docker (external network /
      host-gateway cho WSL).
- [ ] `CHANGELOG.md` cập nhật.
- [ ] (Ghi chú, chưa cần code) hướng đọc kết quả chi tiết §6.

---

## 10. Tiêu chí nghiệm thu

1. AI service chạy ở `:8000`. BE chạy ở `:9000`.
2. `curl -F "file=@de.pdf" http://localhost:9000/api/v1/documents` → trả `job_id` + `status=done`
   + `exam_id`, và `GET /api/v1/documents/{job_id}` xem lại được.
3. Tắt AI service rồi gọi lại → BE trả lỗi gọn (`error_code=BE502`, không crash).
4. Đổi `AI_SERVICE_URL` sang URL khác → BE trỏ sang AI mới mà không phải sửa code router.
