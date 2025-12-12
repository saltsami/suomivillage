FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app:/packages"

RUN pip install --no-cache-dir redis httpx pydantic asyncpg

COPY packages /packages
COPY app ./app

CMD ["python", "-m", "app.worker"]
