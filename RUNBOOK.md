# CanW 本地运行手册

## 依赖

- PostgreSQL 16
- Python 3.14 与 `uv`
- Node.js 24 与 npm

可选地先启动本地数据库：

```powershell
docker compose -f docker-compose.dev.yml up -d postgres
```

## 用户端

```powershell
cd backend
Copy-Item .env.example .env
uv sync --dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

另开终端：

```powershell
cd frontend
Copy-Item .env.example .env
npm ci
npm run dev -- --host 127.0.0.1 --port 5174
```

用户端打开 `http://127.0.0.1:5174`。

## 管理员端

```powershell
cd backend_mger
Copy-Item .env.example .env
uv sync --dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8020 --reload
```

另开终端：

```powershell
cd frontend_mger
npm ci
$env:VITE_ADMIN_API_BASE_URL = "http://127.0.0.1:8020/api/admin/v1"
npm run dev -- --host 127.0.0.1 --port 5175
```

管理员端打开 `http://127.0.0.1:5175`。首次管理员需在 `backend_mger/.env` 填写一次性 `CANW_ADMIN_BOOTSTRAP_EMAIL` 与 `CANW_ADMIN_BOOTSTRAP_PASSWORD`；生产环境必须移除这两个变量，并设置独立高强度密钥。

## 验证

```powershell
cd backend; uv run pytest -q; uv run alembic check
cd ../backend_mger; uv run pytest -q
cd ../frontend; npm run build
cd ../frontend_mger; npm run build
```

## 生产前必做

- 关闭 `CAN_WEN_AUTH_DEV_CODE_ENABLED`，配置 SMTP。
- 配置 S3 兼容对象存储后再允许真实文件上传。
- 修改用户端与管理员端的数据库、认证、加密密钥；不要使用示例值。
- 管理员端关闭 `CANW_ADMIN_AUTO_CREATE_SCHEMA`，仅通过 Alembic 迁移数据库。
- 将进程部署到受信任的反向代理之后，并由代理管理 HTTPS、日志和备份。
