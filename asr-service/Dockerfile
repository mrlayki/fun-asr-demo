FROM python:3.10-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY server.py .
COPY .env.example .env

# Expose port
EXPOSE 8001

# Run the service
CMD ["uv", "run", "python", "server.py"]
