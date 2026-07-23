FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/workspace/backend_mger/.venv/bin:$PATH"

RUN pip install --no-cache-dir uv==0.11.16

WORKDIR /workspace/backend_mger

COPY backend_mger/pyproject.toml backend_mger/uv.lock backend_mger/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend_mger/ ./
COPY backend/docs/knowledge/ /workspace/backend/docs/knowledge/

RUN useradd --create-home --uid 10001 canw \
    && mkdir -p /workspace/backend_mger/var/knowledge /data/knowledge \
    && chown -R canw:canw /workspace/backend_mger/var /data/knowledge

USER canw

EXPOSE 8020

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8020"]
