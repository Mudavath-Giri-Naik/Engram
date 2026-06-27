# Engram API — container image for Render / Railway / any Docker host.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EMBEDDING_MODEL=hashing

WORKDIR /app

# System deps kept minimal; psycopg[binary] ships its own libpq.
COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --upgrade pip && pip install .

EXPOSE 8000

# On boot: apply migrations, seed the bootstrap tenant + Qdrant collection, then serve.
# $PORT is provided by Render/Railway; defaults to 8000 locally.
CMD ["sh", "-c", "alembic upgrade head && python -m engram.cli bootstrap && uvicorn engram.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
