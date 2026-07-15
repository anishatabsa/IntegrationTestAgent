FROM python:3.12-slim

WORKDIR /app

# Install system deps (git, javac for healer, curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    default-jdk-headless \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy source
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "aita.main:app", "--host", "0.0.0.0", "--port", "8080"]
