# Use Docker Hub mirror for China mainland access
FROM docker.1ms.run/python:3.12-slim

WORKDIR /app

# System deps for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install uv (using ghcr mirror for China)
COPY --from=ghcr.1ms.run/astral-sh/uv:latest /uv /uvx /bin/

# Copy project definition only (no lockfile — resolve fresh for Linux)
COPY pyproject.toml ./

# Install dependencies only (skip building project package)
RUN uv sync --no-install-project

# Copy application code
COPY server.py .

# FunASR models will be downloaded on first startup into ~/.cache/modelscope
# To persist across restarts, mount a volume to /root/.cache/modelscope

EXPOSE 8001

CMD ["uv", "run", "python", "server.py"]
