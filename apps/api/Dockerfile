FROM python:3.11-slim

WORKDIR /app

# Run as non-root user for security
RUN groupadd -g 10001 photobooth && useradd -u 10001 -g photobooth -m -s /bin/bash photobooth

COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r /app/requirements.txt

COPY apps/api /app/apps/api

# Ensure container data dir exists with proper ownership
RUN mkdir -p /app/data && chown -R photobooth:photobooth /app

USER photobooth

CMD ["uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

