FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 tzdata ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN mkdir -p src
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

COPY src ./src
RUN pip install --no-cache-dir .

# Hint that /data is where persistent state lives (compose handles the bind)
VOLUME ["/data"]

EXPOSE 8000
CMD ["uvicorn", "inbox_backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

