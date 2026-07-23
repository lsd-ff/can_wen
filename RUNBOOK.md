# CanW 本地运行手册

## 依赖

- PostgreSQL 16
- Redis 7、Qdrant、OpenSearch（本地知识构建依赖）
- Neo4j Aura（唯一业务图数据库，通过 `backend_mger/.env` 连接）
- Python 3.14 与 `uv`
- Node.js 24 与 npm

可选地先启动本地数据库：

```powershell
docker compose -f docker-compose.dev.yml up -d postgres
```

启动知识构建依赖：

```powershell
docker compose -f docker-compose.dev.yml up -d redis qdrant opensearch
```

整套 Docker 启动（包含两套数据库迁移、管理 API、Worker 和管理页面）：

```powershell
$env:ADMIN_WEB_PORT = '5176' # 若 5175 没有被占用可省略
docker compose -f docker-compose.dev.yml up -d --build
```

容器 PostgreSQL 默认映射宿主机 `5434`，避免与开发数据库的 `5432` 冲突。

## 用户端

用户问诊会读取管理端已经发布到 Qdrant、OpenSearch 和 Neo4j Aura 的同一份知识。先在 `backend/.env` 中配置：

```powershell
CAN_WEN_KNOWLEDGE_MODEL_API_KEY=<与管理端一致的 Embedding/Rerank 服务密钥>
CAN_WEN_KNOWLEDGE_EMBEDDING_MODEL_ID=text-embedding-v4
CAN_WEN_KNOWLEDGE_EMBEDDING_DIMENSIONS=1024
CAN_WEN_KNOWLEDGE_RERANK_MODEL_ID=qwen3-rerank
CAN_WEN_QDRANT_URL=http://127.0.0.1:6333
CAN_WEN_OPENSEARCH_URL=http://127.0.0.1:9200
CAN_WEN_NEO4J_URI=neo4j+s://<Aura 实例>
CAN_WEN_NEO4J_USER=<Aura 只读账号>
CAN_WEN_NEO4J_PASSWORD=<Aura 密钥>
CAN_WEN_NEO4J_DATABASE=<Aura 数据库>
```

用户端与管理端的 Embedding 模型、维度、集合/索引和 Aura 数据库必须一致。用户端知识模型凭据是服务端共享配置，不能使用终端用户保存的聊天模型密钥代替。

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

问诊的新建、续问、多模态和重新生成入口都通过四智能体 SSE 流返回过程。若管理端还没有审核并发布知识，用户端会明确显示“知识快照不可用”，不会退回纯大模型答案。

## 管理员端

```powershell
cd backend_mger
Copy-Item .env.example .env
uv sync --dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8020 --reload
```

知识构建需要另开 Worker 终端：

```powershell
cd backend_mger
uv run celery -A app.celery_app:celery_app worker --loglevel=INFO --concurrency=2
```

另开终端：

```powershell
cd frontend_mger
npm ci
$env:VITE_ADMIN_API_BASE_URL = "http://127.0.0.1:8020/api/admin/v1"
npm run dev -- --host 127.0.0.1 --port 5175
```

管理员端打开 `http://127.0.0.1:5175`。首次管理员需在 `backend_mger/.env` 填写一次性 `CANW_ADMIN_BOOTSTRAP_EMAIL` 与 `CANW_ADMIN_BOOTSTRAP_PASSWORD`；生产环境必须移除这两个变量，并设置独立高强度密钥。

若管理端已经启动过且新增接口显示 `Not Found`，需要重启对应的管理员 API 进程；Vite 热更新只刷新前端，不会替换一个未使用 `--reload` 启动的旧 FastAPI 进程。确认 `VITE_ADMIN_API_BASE_URL` 与实际 API 端口一致。

## 首批知识文档

```powershell
cd backend_mger
uv run python -m scripts.import_initial_knowledge
```

导入命令按标题、版本和 SHA 幂等。完整技术说明见 `backend_mger/docs/knowledge-build-system.md`。

若整套系统运行在 Docker 中，则执行：

```powershell
$env:INITIAL_KNOWLEDGE_DIR = 'C:\Users\w\Desktop\mrakdown文档\data\05_qa_ready_md'
docker compose -f docker-compose.dev.yml --profile seed run --rm knowledge-seed
```

## 验证

```powershell
cd backend; uv run pytest -q; uv run alembic check
cd ../backend_mger; uv run pytest -q; uv run alembic check
cd ../frontend; npm run build
cd ../frontend_mger; npm run build
cd ../backend_mger; uv run python -m scripts.smoke_knowledge_stores
docker exec canw-admin-api python -m scripts.smoke_knowledge_e2e
```

用户端四智能体架构、路由/上下文规则、检索循环、事件协议和降级策略见 `backend/docs/diagnosis-agent-architecture.md`。

最后一条命令要求完整 Docker 栈正在运行，并要求 `backend_mger/.env` 已配置 Neo4j Aura。它会调用少量真实模型，并在验证异步构建、审核、发布、Qdrant、OpenSearch 与 Aura 后自动清理隔离验收数据。

MinerU 真实文件验收可使用一份包含明确标题、表格和已知文本的小型 PDF：

```powershell
docker cp C:\path\to\small-sample.pdf canw-admin-api:/tmp/mineru-smoke.pdf
docker exec canw-admin-api python -m scripts.smoke_mineru /tmp/mineru-smoke.pdf --expect 预期文本
docker exec canw-admin-api rm -f /tmp/mineru-smoke.pdf
```

该脚本验证 MinerU 签名上传、异步轮询、结果下载、Markdown 结构与后续切分，并自动清理数据库和知识对象存储中的验收数据；命令会消耗一次 MinerU 文档解析额度。

## 生产前必做

- 关闭 `CAN_WEN_AUTH_DEV_CODE_ENABLED`，配置 SMTP。
- 配置 S3 兼容对象存储后再允许真实文件上传。
- 轮换曾在聊天或终端中暴露过的 MinerU、DashScope Token，并将正式密钥迁移到密钥管理服务。
- 为 Qdrant、OpenSearch 配置认证、备份、资源上限和内网访问策略，并为 Neo4j Aura 配置最小权限账号、备份与密钥轮换。
- 修改用户端与管理员端的数据库、认证、加密密钥；不要使用示例值。
- 管理员端关闭 `CANW_ADMIN_AUTO_CREATE_SCHEMA`，仅通过 Alembic 迁移数据库。
- 将进程部署到受信任的反向代理之后，并由代理管理 HTTPS、日志和备份。
