FROM python:3.11-slim

WORKDIR /app

# Install the shared, hash-locked runtime dependency set.
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

# Copy shared packages
COPY packages /app/packages

# Copy service code
COPY services/decision_service/app /app/app

ENV PYTHONPATH=/app

CMD ["python", "-m", "app.main"]
