FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

RUN pip install --no-cache-dir pydantic redis asyncpg

COPY packages ./packages
COPY services/engine/app ./app

CMD ["python", "-m", "app.runner"]
