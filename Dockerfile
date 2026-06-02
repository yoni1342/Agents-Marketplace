FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal — psycopg[binary] ships its own libpq.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8002

# Run migrations then boot. In production prefer running the migration as a
# separate step/job; this keeps single-container deploys simple.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8002"]
