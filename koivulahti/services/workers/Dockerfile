FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

RUN pip install --no-cache-dir redis httpx pydantic pydantic-settings asyncpg

COPY packages ./packages
COPY services/workers/app ./app

CMD ["python", "-m", "app.worker"]
