FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd --create-home appuser && \
    mkdir -p /app/backups && \
    chown -R appuser:appuser /app
USER appuser

# Run migrations and start the application
CMD ["sh", "-c", "python -m alembic upgrade head && python run.py"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()" || exit 1
