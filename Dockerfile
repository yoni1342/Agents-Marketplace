# Agent Marketplace catalog service (FastAPI + SQLModel + Alembic, :8002).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Deps first for layer caching. psycopg[binary] ships its own libpq, so no
# system build deps are needed.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# App + migrations + git-authored specs (examples/docs are dev-only).
COPY app ./app
COPY alembic ./alembic
COPY specs ./specs
COPY alembic.ini ./

EXPOSE 8002

# NOTE on the M5 eval gate: it shells out to the `claude` CLI, which is NOT in
# this image. To run the gate inside a container, mount the host CLI + its auth
# (e.g. -v /root/.local/bin/claude:/usr/local/bin/claude:ro and the claude
# config/credentials dir) at runtime. Without it, `is_configured()` is False
# and publishing a spec WITH eval_cases is blocked (fail-closed) — publish such
# specs from a host/CI that has the CLI, or via ?allow_uneval=true.

# Migrate, sync git-authored specs into the DB, then boot. The sync currently
# uses --allow-uneval because this image doesn't ship the claude CLI; the
# stronger gate should run earlier in CI or from a host with the CLI present.
CMD ["sh", "-c", "alembic upgrade head && python -m app.cli sync specs --allow-uneval && uvicorn app.main:app --host 0.0.0.0 --port 8002"]
