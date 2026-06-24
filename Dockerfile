FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Use UV since you have uv.lock, otherwise fallback to pip
RUN pip install uv

# Copy dependencies first for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Copy the rest of the application
COPY . .

# Expose the API port
EXPOSE 8000

# Set UV environment path
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]