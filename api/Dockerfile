# AI Front Desk API — FastAPI + LangGraph
FROM python:3.13-slim

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install deps first (layer-cached) then app code
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project

COPY app ./app

EXPOSE 8000
# Honor Railway's injected $PORT (default 8000 for compose). Bind 0.0.0.0 (IPv4)
# locally so compose service discovery (`api:8000`) works; bind :: on Railway,
# whose private network is IPv6-only — auto-detected via the Railway-injected
# RAILWAY_PRIVATE_DOMAIN, and overridable with UVICORN_HOST. Shell form so the
# vars expand.
CMD ["sh", "-c", "HOST=\"${UVICORN_HOST:-0.0.0.0}\"; if [ -z \"$UVICORN_HOST\" ] && [ -n \"$RAILWAY_PRIVATE_DOMAIN\" ]; then HOST=::; fi; exec uv run --no-dev uvicorn app.main:app --host \"$HOST\" --port \"${PORT:-8000}\""]
