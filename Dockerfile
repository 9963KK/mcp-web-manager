# Multi-stage build for MCP Web Manager
# Runtime: Python backend (FastAPI+Uvicorn) + static frontend

# ---------- Prepare frontend ----------
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
# 由于项目使用纯 HTML 架构，直接复制静态文件，无需复杂构建
COPY frontend/public ./dist

# ---------- Build backend (venv) ----------
FROM python:3.12-slim AS backend-build
ENV PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/pyproject.toml backend/ ./backend/
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/python - <<'PY'
from pathlib import Path
import tomllib
p = tomllib.loads(Path('backend/pyproject.toml').read_text())
reqs = p.get('project', {}).get('dependencies', [])
Path('/tmp/reqs.txt').write_text('\n'.join(reqs))
print('Wrote /tmp/reqs.txt with', len(reqs), 'deps')
PY
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/reqs.txt
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
# mcp-proxy sources removed; backend.core is used at runtime

# Copy frontend static files into the path backend expects (/app/frontend/public)
COPY --from=frontend-build /app/frontend/dist/ /app/frontend/public/

# Expose service port
EXPOSE 8765

# Default envs
ENV PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////app/backend/mcp_web_manager.db

# Install backend runtime dependencies (from pyproject)
RUN /opt/venv/bin/python - <<'PY'
from pathlib import Path
import tomllib
p = tomllib.loads(Path('/app/backend/pyproject.toml').read_text())
reqs = p.get('project', {}).get('dependencies', [])
Path('/tmp/reqs.txt').write_text('\n'.join(reqs))
PY
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/reqs.txt

# Start command
WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8765"]

