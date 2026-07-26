# Build context is the `aisle/` project root (see docker-compose.yml's
# `build.context: .` + `dockerfile: backend/Dockerfile`), because the backend
# needs sibling config/, taxonomy/, prompts/, data/ directories at runtime —
# aisle/backend/aisle/settings.py resolves REPO_ROOT to /app from here, which
# is why the directory layout below mirrors the host layout exactly.
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc curl && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY config/ config/
COPY taxonomy/ taxonomy/
COPY prompts/ prompts/
COPY data/ data/

WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "aisle.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
