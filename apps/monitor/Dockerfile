FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY core ./core
COPY providers ./providers
COPY agents ./agents
COPY apps/monitor ./apps/monitor
COPY apps/api/routers/market.py ./apps/api/routers/market.py
COPY apps/api/__init__.py apps/api/routers/__init__.py ./apps/api/
COPY config ./config

RUN adduser --disabled-password orion && chown -R orion /app
USER orion

CMD ["python", "-m", "apps.monitor.main"]
