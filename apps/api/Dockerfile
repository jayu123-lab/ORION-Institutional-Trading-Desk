FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY core ./core
COPY providers ./providers
COPY agents ./agents
COPY apps/api ./apps/api
COPY config ./config
COPY database/schema.sql ./database/schema.sql

RUN adduser --disabled-password orion && chown -R orion /app
USER orion

EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
