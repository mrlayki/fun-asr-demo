FROM python:3.10-slim

WORKDIR /app

# System deps for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project definition
COPY pyproject.toml ./

# Install dependencies (resolve fresh for Linux platform)
RUN uv sync --no-dev

# Copy application code
COPY server.py .

# FunASR models will be downloaded on first startup into ~/.cache/modelscope
# To persist across restarts, mount a volume to /root/.cache/modelscope

EXPOSE 8001

CMD ["uv", "run", "python", "server.py"]
