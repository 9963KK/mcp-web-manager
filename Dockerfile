# Multi-stage build for MCP Web Manager
# Runtime: Python backend (FastAPI+Uvicorn) + static frontend

# ---------- Build frontend ----------
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm i
COPY frontend .
RUN npm run build

# ---------- Build backend (venv) ----------
FROM python:3.12-slim AS backend-build
ENV PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/pyproject.toml backend/ ./backend/
RUN python -m venv /opt/venv && . /opt/venv/bin/activate && pip install --upgrade pip && \
    python - <<'PY'
from pathlib import Path
import tomllib
p = tomllib.loads(Path('backend/pyproject.toml').read_text())
reqs = p.get('project', {}).get('dependencies', [])
Path('/tmp/reqs.txt').write_text('\n'.join(reqs))
print('Wrote /tmp/reqs.txt with', len(reqs), 'deps')
PY
    && . /opt/venv/bin/activate && pip install --no-cache-dir -r /tmp/reqs.txt
# Copy backend source
COPY backend /app/backend

# ---------- Final runtime image ----------
FROM python:3.12-slim
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app

# Create venv and install runtime deps (again for portability)
RUN python -m venv /opt/venv && . /opt/venv/bin/activate && pip install --upgrade pip

# Copy backend and install via dependencies
COPY --from=backend-build /app/backend /app/backend
# Include local mcp-proxy sources to PYTHONPATH at runtime
COPY mcp-proxy /app/mcp-proxy

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist /app/frontend/public/dist

# Expose service port
EXPOSE 8765

# Default envs
ENV PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////app/backend/mcp_web_manager.db

# Install backend runtime dependencies (from pyproject)
RUN python - <<'PY'
from pathlib import Path
import tomllib, subprocess
p = tomllib.loads(Path('/app/backend/pyproject.toml').read_text())
reqs = p.get('project', {}).get('dependencies', [])
open('/tmp/reqs.txt','w').write('\n'.join(reqs))
PY
 && . /opt/venv/bin/activate && pip install --no-cache-dir -r /tmp/reqs.txt

# Start command
WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8765"]

