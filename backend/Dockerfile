# Build context is the `aisle/` project root (see docker-compose.yml's
# `build.context: .` + `dockerfile: backend/Dockerfile`), because the backend
# needs sibling config/, taxonomy/, prompts/, data/ directories at runtime —
# aisle/backend/aisle/settings.py resolves REPO_ROOT to /app from here, which
# is why the directory layout below mirrors the host layout exactly.
FROM python:3.11-slim

WORKDIR /app

# No apt-get/gcc layer: every package in requirements.txt — including the
# ones most likely to need a C extension build (hdbscan, umap-learn's
# pynndescent/llvmlite, scikit-learn, scipy, torch via sentence-transformers)
# — ships a prebuilt cp311-manylinux wheel, verified with
# `pip download --only-binary=:all: -r backend/requirements.txt`. The one
# package without a wheel (langdetect) is pure Python, so its sdist build
# needs no compiler either. curl was likewise unused: no HEALTHCHECK or
# runtime code in this image shells out to it. Dropping this layer removes
# the exact RUN step that was OOM-killing/crashing the Railway build.
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
