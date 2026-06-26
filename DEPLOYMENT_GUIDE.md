# DevSecOps Auto Ticket Deployment Guide

Guide này mô tả quy trình build, CI/CD, chuẩn bị EC2, cấu hình `.env`, và chạy
ứng dụng bằng Docker Compose.

Không commit file `.env` thật lên GitHub.

## 1. Trạng thái CI/CD hiện tại

Project dùng GitHub Actions, không dùng GitLab CI.

Workflow nằm ở:

```text
.github/workflows/ci.yml
```

Các job chính:

| Job | Mục đích |
|---|---|
| `secret-guard` | Chặn `.env`, private key, credential JSON, token hardcode bị commit |
| `unit-tests` | Cài `requirements-dev.txt` và chạy `pytest` |
| `docker-build` | Build Docker image |
| `docker-publish` | Push image lên GitHub Container Registry khi push vào `main` |

Nếu IDE vẫn đang mở `.gitlab-ci.yml`, có thể đóng tab đó. File này không còn
dùng trong hướng GitHub Actions.

## 2. Kiểm tra secret trước khi commit

Chạy từ thư mục project:

```bash
cd /Users/quyph/Documents/Devsecops_auto_ticket
git check-ignore -v .env
git ls-files -- .env
```

Kết quả an toàn:

- `git check-ignore -v .env` có hiện rule trong `.gitignore`.
- `git ls-files -- .env` không in gì.

Không chạy:

```bash
git add -f .env
```

## 3. Build và test local

Chạy unit test:

```bash
cd /Users/quyph/Documents/Devsecops_auto_ticket
.venv/bin/python -m pytest -q
```

Build Docker image:

```bash
docker compose build app migrate
```

Start PostgreSQL:

```bash
docker compose up -d postgres
docker compose ps
```

Chạy migration:

```bash
docker compose run --rm migrate
```

Kiểm tra migration:

```bash
docker compose run --rm migrate alembic current
```

Kết quả mong muốn:

```text
20260625_0002 (head)
```

Start app:

```bash
docker compose up -d app
docker compose logs -f app
```

Kiểm tra health:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/db
```

## 4. Lưu ý PostgreSQL local port

Trong `docker-compose.yml`, PostgreSQL đang map:

```text
127.0.0.1:5433 -> container postgres:5432
```

Vì vậy:

- Container app/migrate dùng `postgres:5432`.
- Máy host kết nối qua `127.0.0.1:5433`.

Trong `.env` cho Docker Compose, giữ:

```env
DATABASE_URL=postgresql+psycopg://devsecops:devsecops@postgres:5432/devsecops
```

Nếu dùng `psql` từ máy host:

```bash
psql -h 127.0.0.1 -p 5433 -U devsecops -d devsecops
```

## 5. Push lên GitHub

Remote GitHub nên trỏ về:

```text
https://github.com/n21dcvt084-tech/Devsecops_auto_ticket.git
```

Kiểm tra:

```bash
git remote -v
```

Commit và push:

```bash
git status --short
git add -A
git commit -m "Add deployment guide"
git push origin main
```

Sau khi push, vào GitHub:

```text
Repository -> Actions
```

Kiểm tra workflow chạy pass.

Nếu job `docker-publish` lỗi quyền push package, vào:

```text
Repository -> Settings -> Actions -> General -> Workflow permissions
```

Chọn:

```text
Read and write permissions
```

## 6. Có cần bật EC2 ngay không?

Chưa cần bật EC2 ngay nếu GitHub Actions chưa pass.

Thứ tự nên làm:

1. Test local pass.
2. Docker Compose local chạy được.
3. Push GitHub.
4. GitHub Actions pass.
5. Docker image publish được lên GHCR.
6. Sau đó mới bật EC2 để deploy.

Làm theo thứ tự này giúp tránh debug cùng lúc cả app, CI, Docker image, mạng
AWS, security group, và secrets.

## 7. Chuẩn bị EC2

Khuyến nghị ban đầu:

| Thành phần | Gợi ý |
|---|---|
| OS | Ubuntu 22.04 hoặc 24.04 |
| Instance | `t3.small` để test, `t3.medium` nếu workload lớn hơn |
| Disk | 20-30 GB |
| SSH port `22` | Chỉ mở IP của bạn |
| App port `8000` | Chỉ mở IP của bạn trong giai đoạn test |
| Production | Dùng Nginx + HTTPS port `443` |

Cài Docker trên EC2:

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Đăng xuất SSH rồi đăng nhập lại để group `docker` có hiệu lực.

## 8. Cấu hình `.env` trên EC2

Tạo `.env` trực tiếp trên EC2. Không commit file này.

Ví dụ khung cấu hình:

```env
# DefectDojo
DEFECTDOJO_BASE_URL=https://your-defectdojo.example.com
DEFECTDOJO_API_TOKEN=<real_defectdojo_token>
DEFECTDOJO_FINDINGS_LIMIT=100
DEFECTDOJO_REQUEST_TIMEOUT_SECONDS=60

# Scheduler
SCHEDULER_INTERVAL_SECONDS=300
PROCESSING_CLAIM_TTL_SECONDS=1800

# Database
POSTGRES_PASSWORD=<strong_db_password>
DATABASE_URL=postgresql+psycopg://devsecops:<strong_db_password>@postgres:5432/devsecops

# Project mapping
PROJECT_EMAIL_MAPPING_FILE=config/project_mapping.json

# SMTP
SMTP_HOST=<smtp_host>
SMTP_PORT=587
SMTP_USERNAME=<smtp_username>
SMTP_PASSWORD=<smtp_password>
SMTP_FROM_EMAIL=DevSecOps Automation <devsecops@example.com>
SMTP_USE_TLS=true
SMTP_TIMEOUT_SECONDS=30
SMTP_MAX_EMAILS_PER_MINUTE=30
SMTP_MAX_EMAILS_PER_HOUR=500
SMTP_MAX_ATTEMPTS=3
SMTP_RETRY_DELAY_SECONDS=60
SMTP_RETRY_BACKOFF_MULTIPLIER=2

# ManageEngine
MANAGEENGINE_DELIVERY_MODE=email_fetch
MANAGEENGINE_DRY_RUN=true
MANAGEENGINE_PUBLIC_URL=https://your-manageengine.example.com

# API mode only
MANAGEENGINE_BASE_URL=https://your-manageengine.example.com
MANAGEENGINE_AUTH_TOKEN=<real_manageengine_token>
MANAGEENGINE_REQUEST_TIMEOUT_SECONDS=30
MANAGEENGINE_VERIFY_SSL=true
MANAGEENGINE_REQUESTER_NAME=administrator
MANAGEENGINE_REQUESTER_EMAIL=
MANAGEENGINE_DEFAULT_GROUP=
MANAGEENGINE_DEFAULT_CATEGORY=
MANAGEENGINE_DEFAULT_SUBCATEGORY=
```

Quan trọng:

- `POSTGRES_PASSWORD` và password trong `DATABASE_URL` phải giống nhau.
- Nếu dùng Docker Compose, DB host là `postgres`, không phải `localhost`.
- Ban đầu giữ `MANAGEENGINE_DRY_RUN=true`.
- Chỉ đổi `MANAGEENGINE_DRY_RUN=false` sau khi đã test routing, SMTP, và ticket
  flow cẩn thận.

## 9. Deploy trên EC2 bằng Docker Compose

Clone repo:

```bash
git clone https://github.com/n21dcvt084-tech/Devsecops_auto_ticket.git
cd Devsecops_auto_ticket
```

Tạo `.env`:

```bash
cp .env.example .env
nano .env
```

Build và chạy:

```bash
docker compose build app migrate
docker compose up -d postgres
docker compose run --rm migrate
docker compose up -d app
docker compose ps
```

Kiểm tra:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/db
```

Xem log:

```bash
docker compose logs -f app
```

Stop app:

```bash
docker compose stop app
```

Stop toàn bộ:

```bash
docker compose down
```

Không dùng `docker compose down -v` nếu không muốn xóa dữ liệu PostgreSQL.

## 10. Deploy bằng image từ GitHub Container Registry

Sau khi GitHub Actions publish image, image sẽ có dạng:

```text
ghcr.io/n21dcvt084-tech/devsecops_auto_ticket:latest
ghcr.io/n21dcvt084-tech/devsecops_auto_ticket:<commit-sha>
```

Nếu repo/package private, EC2 cần login GHCR:

```bash
echo "<github_token>" | docker login ghcr.io -u "<github_username>" --password-stdin
```

Token cần quyền đọc package.

Giai đoạn đầu có thể build trực tiếp trên EC2 bằng `docker compose build` cho
đơn giản. Khi flow ổn định rồi mới chuyển sang pull image từ GHCR.

## 11. Troubleshooting nhanh

### Lỗi: failed to resolve host `postgres`

Nguyên nhân thường gặp:

- Chạy `alembic upgrade head` trực tiếp trên máy host.
- Chạy container bằng `docker run` không nằm trong Compose network.

Cách đúng:

```bash
docker compose run --rm migrate
```

Nếu muốn chạy từ máy host, `DATABASE_URL` phải dùng `127.0.0.1:5433`, nhưng
không khuyến nghị cho flow Docker Compose chuẩn.

### Lỗi: Bind for 127.0.0.1:5432 failed

Port `5432` trên máy host đã bị PostgreSQL/container khác chiếm.

Project đã đổi sang host port `5433`. Kiểm tra:

```bash
docker compose ps
```

Kết quả mong muốn:

```text
127.0.0.1:5433->5432/tcp
```

### Health DB trả `503`

Kiểm tra:

```bash
docker compose ps
docker compose logs postgres
docker compose logs app
docker compose run --rm migrate alembic current
```

Migration phải ở:

```text
20260625_0002 (head)
```

### App gửi email/tạo ticket ngoài ý muốn

Scheduler chạy ngay khi app start. Trước khi chạy app thật, kiểm tra `.env`:

```env
MANAGEENGINE_DRY_RUN=true
SCHEDULER_INTERVAL_SECONDS=300
```

Nếu chỉ muốn kiểm tra database/migration, chưa start `app`:

```bash
docker compose up -d postgres
docker compose run --rm migrate
```
