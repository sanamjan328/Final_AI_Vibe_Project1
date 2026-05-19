# Stage 1: Build Next.js static export
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build
# Output is in /app/frontend/out/

# Stage 2: Python backend
FROM python:3.12-slim AS final
WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy backend manifest and lockfile, install deps into a project venv
COPY backend/pyproject.toml backend/uv.lock ./backend/
WORKDIR /app/backend
RUN uv sync --frozen --no-dev

# Copy backend source
COPY backend/ .

# Copy frontend static build into the backend's static directory
COPY --from=frontend-builder /app/frontend/out/ ./static/

# Runtime setup
WORKDIR /app
ENV PYTHONPATH=/app/backend
ENV DB_PATH=/app/db/finally.db

EXPOSE 8000

CMD ["uv", "run", "--directory", "/app/backend", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
