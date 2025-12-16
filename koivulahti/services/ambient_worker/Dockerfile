FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

RUN pip install --no-cache-dir asyncpg pydantic pydantic-settings

COPY packages ./packages
COPY services/ambient_worker/app ./app

CMD ["python", "-m", "app.worker"]
