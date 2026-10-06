FROM python:3.12-slim

WORKDIR /app

# Set production environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create non-root user and persistent directories
RUN useradd --create-home appuser && \
    mkdir -p /app/data /app/backups && \
    chown -R appuser:appuser /app && \
    chmod +x /app/docker-entrypoint.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "run.py"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, httpx; p = os.environ.get('PORT', '8000'); httpx.get(f'http://localhost:{p}/health').raise_for_status()" || exit 1
