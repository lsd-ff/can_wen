# CanW 管理员 API

独立的 FastAPI 管理服务，与用户端共用 PostgreSQL 和对象存储。管理员身份、会话、权限、审计和专家复核数据保存在 PostgreSQL 的 `admin` schema。知识中心已包含 LangGraph RAG/KG 双智能体、Celery Worker、人工审核和 Qdrant/OpenSearch/Neo4j Aura 幂等发布链路；Aura 是唯一业务图数据库。

完整设计与数据流见 [docs/knowledge-build-system.md](docs/knowledge-build-system.md)。

当前双智能体不是固定的“模型调用脚本”：总控图包含文档规划和 targets 条件路由；RAG、KG 子图分别包含质量判断、最多两轮反思修正、专家模型与人工审核分流。构建详情 API 会返回结构化计划、工具调用、风险路由、修正轮次及 Chunk 级决策，管理端“构建任务”可直接查看完整运行轨迹。反思轮次可通过 `CANW_ADMIN_KNOWLEDGE_MAX_REFLECTION_ROUNDS` 配置，默认 `2`。

## 启动

```powershell
cd D:\agent_project\can_wen\backend_mger
uv sync --dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8020
```

知识构建 Worker 需要单独启动：

```powershell
cd D:\agent_project\can_wen\backend_mger
uv run celery -A app.celery_app:celery_app worker --loglevel=INFO --concurrency=2
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

生产环境必须设置独立的 `CANW_ADMIN_AUTH_SECRET_KEY`、`CANW_ADMIN_ENCRYPTION_KEY`，并关闭 `CANW_ADMIN_AUTO_CREATE_SCHEMA`。MinerU 与模型密钥只放在被 Git 忽略的 `.env` 或正式密钥管理服务中。
