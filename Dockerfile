# Nexo dashboard image (for a future GCP Cloud Run deployment — NOT deployed here).
# Build:  docker build -t nexo-os .
# Run:    docker run -p 8080:8080 --env-file .env nexo-os
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

COPY pyproject.toml README.md ./
COPY nexo_os ./nexo_os
RUN pip install --upgrade pip && pip install -e .

# Generate synthetic data at build time so the image is self-contained for a demo.
# For production (BigQuery), set NEXO_DATA_SOURCE=bigquery and skip this.
RUN python -m nexo_os seed

EXPOSE 8080

# Cloud Run provides $PORT. Streamlit binds to it.
CMD ["sh", "-c", "streamlit run nexo_os/dashboard/app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true"]
