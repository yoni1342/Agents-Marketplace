# Agent Marketplace catalog service (FastAPI + SQLModel + Alembic, :8002).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Deps first for layer caching. psycopg[binary] ships its own libpq, so no
# system build deps are needed.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# App + migrations (examples/docs are dev-only — see .dockerignore).
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8002

# NOTE on the M5 eval gate: it shells out to the `claude` CLI, which is NOT in
# this image. To run the gate inside a container, mount the host CLI + its auth
# (e.g. -v /root/.local/bin/claude:/usr/local/bin/claude:ro and the claude
# config/credentials dir) at runtime. Without it, `is_configured()` is False
# and publishing a spec WITH eval_cases is blocked (fail-closed) — publish such
# specs from a host/CI that has the CLI, or via ?allow_uneval=true.

# Migrate then boot. For multi-replica deploys, run the migration as a separate
# one-shot job instead and drop the `alembic upgrade` here.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8002"]
