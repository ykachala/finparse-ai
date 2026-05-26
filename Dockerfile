FROM python:3.12-slim

# Install system dependencies required by pdf2image (poppler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["python", "-m", "src"]
