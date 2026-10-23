# Backend API image for Google Cloud Run.
# Built from the repository root because the image needs both backend/ and the
# validated seed files in data/seed/ (used by the migrate-and-seed job).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY data/seed /app/data/seed

RUN useradd --system --uid 10001 appuser
USER appuser

# Cloud Run provides PORT (default 8080). --proxy-headers trusts Cloud Run's front end.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
