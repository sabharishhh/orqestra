FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y gcc libpq-dev g++ && rm -rf /var/lib/apt/lists/*

# Install UV
RUN pip install uv

# --- THE FIX ---
# Copy .python-version alongside the lockfiles so UV strictly uses 3.13
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen

RUN uv run python -m spacy download en_core_web_sm

# Copy the rest of the application
COPY . .

# Expose the API port
EXPOSE 8000

# Set UV environment path
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]