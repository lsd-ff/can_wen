# Can Wen Backend

FastAPI backend for the Can Wen project.

## Setup

```powershell
cd backend
uv sync --dev
```

## Run

```powershell
uv run uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

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
  -Uri http://127.0.0.1:8000/api/v1/auth/email/verification-codes `
  -ContentType "application/json" `
  -Body '{"email":"user@qq.com"}'
```

Login with the code:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/auth/email/login `
  -ContentType "application/json" `
  -Body '{"email":"user@qq.com","code":"123456","device_name":"Chrome"}'
```

Logout:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/auth/logout `
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
```

## Add Packages

Runtime dependencies:

```powershell
uv add package-name
```

Development dependencies:

```powershell
uv add --dev package-name
```
