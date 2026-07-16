FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY services/decision_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared packages
COPY packages /app/packages

# Copy service code
COPY services/decision_service/app /app/app

ENV PYTHONPATH=/app

CMD ["python", "-m", "app.main"]
