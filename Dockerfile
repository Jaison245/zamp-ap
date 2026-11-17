# syntax=docker/dockerfile:1

# ---- Stage 1: build the React UI --------------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime (serves API + built UI on one port) ------------
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    EXTRACTOR=auto
WORKDIR /app

# Python deps first (better layer caching)
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# App code + demo fixtures
COPY backend/ backend/
COPY data/ data/
COPY invoices/ invoices/
COPY scripts/ scripts/
COPY eval.py ./

# Built UI from stage 1
COPY --from=frontend /app/frontend/dist frontend/dist

RUN mkdir -p uploads

# Hosts (Render / Railway / Fly / HF Spaces) inject $PORT; default 8000 locally.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
