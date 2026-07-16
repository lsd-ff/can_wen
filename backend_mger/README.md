# CanW 管理员 API

独立的 FastAPI 管理服务，与用户端共用 PostgreSQL 和对象存储。管理员身份、会话、权限、审计和专家复核数据保存在 PostgreSQL 的 `admin` schema。

## 启动

```powershell
cd D:\agent_project\can_wen\backend_mger
uv sync --dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8020
```

```powershell
cd D:\agent_project\can_wen\frontend_mger
npm install
$env:VITE_ADMIN_API_BASE_URL = "http://127.0.0.1:8020/api/admin/v1"
npm run dev
```

开发时可将 `.env.example` 复制为 `.env`。`CANW_ADMIN_CORS_ORIGINS` 使用 JSON 数组格式，可在生产环境加入实际管理端域名。

开发环境可通过环境变量创建首个超级管理员：

```powershell
$env:CANW_ADMIN_BOOTSTRAP_EMAIL = "admin@example.com"
$env:CANW_ADMIN_BOOTSTRAP_PASSWORD = "Change-this-before-production"
```

生产环境必须设置独立的 `CANW_ADMIN_AUTH_SECRET_KEY`、`CANW_ADMIN_ENCRYPTION_KEY`，并关闭 `CANW_ADMIN_AUTO_CREATE_SCHEMA`。
