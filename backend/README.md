# Can Wen Backend

FastAPI backend for the Can Wen project.

## Setup

```powershell
cd backend
uv sync --dev
```

## Run

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

The API will be available at `http://127.0.0.1:8010`.

## Evidence-first diagnosis agents

Authenticated diagnosis conversations use a four-agent LangGraph workflow: context/routing, KG Agentic Query, HNSW+BM25 Agentic Query, and evidence governance/grounded answering. The process is streamed to the frontend with SSE and persisted for replay. The legacy direct-model `/api/v1/diagnosis/chat` endpoint has been removed from the router and OpenAPI contract.

Query-side Qdrant, OpenSearch, Neo4j Aura, embedding and rerank settings are documented in `.env.example`. They must match the management-side publication pipeline. See `docs/diagnosis-agent-architecture.md` for the full design and failure policy.

## Published knowledge graph

Authenticated user clients can explore the real Neo4j graph through the read-only endpoints `GET /api/v1/knowledge/graph` and `GET /api/v1/knowledge/graph/detail`. The API exposes only the approved disease-domain schema and public evidence fields. It includes curated legacy relationships without a publication identifier plus relationships belonging to the management side's current publication snapshot; stale published versions remain hidden.

## Database

Configure the database connection with:

```powershell
CAN_WEN_DATABASE_URL=postgresql+psycopg://canwen:canwen123@127.0.0.1:5432/can_wen
```

Start PostgreSQL with Docker:

```powershell
docker run --name can-wen-postgres `
  -e POSTGRES_USER=canwen `
  -e POSTGRES_PASSWORD=canwen123 `
  -e POSTGRES_DB=can_wen `
  -p 5432:5432 `
  -v can-wen-postgres-data:/var/lib/postgresql/data `
  -d postgres:16
```

Open a PostgreSQL shell:

```powershell
docker exec -it can-wen-postgres psql -U canwen -d can_wen
```

Common commands:

```powershell
docker start can-wen-postgres
docker stop can-wen-postgres
docker logs can-wen-postgres
```

Run migrations:

```powershell
uv run alembic upgrade head
```

Create a new migration after changing ORM models:

```powershell
uv run alembic revision --autogenerate -m "describe change"
```

## Email Login

Supported domains for now:

```text
qq.com
vip.qq.com
foxmail.com
163.com
126.com
yeah.net
188.com
vip.163.com
vip.126.com
```

Request a login code:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8010/api/v1/auth/email/verification-codes `
  -ContentType "application/json" `
  -Body '{"email":"user@qq.com"}'
```

Login with the code:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8010/api/v1/auth/email/login `
  -ContentType "application/json" `
  -Body '{"email":"user@qq.com","code":"123456","device_name":"Chrome"}'
```

Logout:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8010/api/v1/auth/logout `
  -ContentType "application/json" `
  -Body '{"refresh_token":"your-refresh-token"}'
```

Local development returns `dev_code` from the verification-code API when SMTP is not configured.

Configure SMTP when real email delivery is needed:

```powershell
CAN_WEN_SMTP_HOST=smtp.example.com
CAN_WEN_SMTP_PORT=465
CAN_WEN_SMTP_USERNAME=your-account@example.com
CAN_WEN_SMTP_PASSWORD=your-smtp-password
CAN_WEN_SMTP_FROM_EMAIL=your-account@example.com
CAN_WEN_SMTP_USE_SSL=true
CAN_WEN_AUTH_DEV_CODE_ENABLED=false
```

## Tests

```powershell
uv run pytest
uv run alembic check
```

## Security defaults

- Per-process API and authentication rate limits are enabled by default. Configure
  `CAN_WEN_API_RATE_LIMIT_REQUESTS_PER_MINUTE` and
  `CAN_WEN_AUTH_RATE_LIMIT_REQUESTS_PER_MINUTE` for the deployment size.
- User-managed model API keys are encrypted with AES-GCM at rest. Rotate
  `CAN_WEN_AUTH_SECRET_KEY` only with a planned key-rotation process.
- Security response headers are on by default and can be controlled with
  `CAN_WEN_SECURITY_HEADERS_ENABLED`.

## Add Packages

Runtime dependencies:

```powershell
uv add package-name
```

Development dependencies:

```powershell
uv add --dev package-name
```
