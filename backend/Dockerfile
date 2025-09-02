FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./

# Ensure egg_base exists so setuptools doesn't fail
RUN mkdir -p src

# Install dependencies (and a tiny empty wheel for now)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Now copy the actual source (this layer changes often)
COPY src ./src

# Reinstall to include your code (still non-editable)
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "inbox_backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

