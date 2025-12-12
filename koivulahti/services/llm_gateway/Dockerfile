FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx pydantic pydantic-settings

COPY packages ./packages
COPY services/llm_gateway/app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
