FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

RUN pip install --no-cache-dir fastapi uvicorn[standard] asyncpg

COPY packages ./packages
COPY services/api/app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8082"]
