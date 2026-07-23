FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/workspace/backend/.venv/bin:$PATH"

RUN pip install --no-cache-dir uv==0.11.16

WORKDIR /workspace/backend

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./

RUN useradd --create-home --uid 10002 canw-user
USER canw-user

CMD ["alembic", "upgrade", "head"]
