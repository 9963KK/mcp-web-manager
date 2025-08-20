# Multi-stage build: prepare frontend static, then build Python runtime

# ---------- Frontend static (no build step; copy public as dist) ----------
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/public ./dist

# ---------- Python runtime ----------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:/root/.local/bin:$PATH"

WORKDIR /app

# Create venv and upgrade pip
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip
# Install common CLI tools required by typical MCP servers: curl, git, Node.js (npx), uv (uvx)
# - curl: debugging and some scripts use it
# - git: many uvx/npx installers fetch from git
# - Node.js 20: provides node and npx for JS MCP servers
# - uv: Python package manager that provides `uvx` runner
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg git \
 && mkdir -p /etc/apt/keyrings \
 && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
 && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends nodejs \
 && curl -LsSf https://astral.sh/uv/install.sh | sh \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*


# Copy backend dependency spec and install
COPY backend/pyproject.toml /app/backend/pyproject.toml
RUN python - <<'PY'
from pathlib import Path
import tomllib
p = tomllib.loads(Path('/app/backend/pyproject.toml').read_text())
reqs = p.get('project', {}).get('dependencies', [])
Path('/tmp/reqs.txt').write_text('\n'.join(reqs))
print('deps:', len(reqs))
PY
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/reqs.txt

# Copy backend source
COPY backend /app/backend

# Copy frontend static to backend-expected path
COPY --from=frontend-build /app/frontend/dist/ /app/frontend/public/

# Data directory for SQLite persistence
RUN mkdir -p /data

# Default envs (can be overridden by docker run/compose)
ENV DATABASE_URL=sqlite:////data/mcp_web_manager.db

# Expose API port
EXPOSE 8765

# Healthcheck using Python stdlib (avoid installing curl)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys;\n\
    import os;\n\
    url='http://127.0.0.1:8765/health';\n\
    sys.exit(0) if urllib.request.urlopen(url, timeout=2).status==200 else sys.exit(1)"

# Run API
WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8765"]

