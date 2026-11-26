# Build context: repository root.  docker build -f services/backup/Dockerfile .
# Nightly pg_dump → S3-compatible bucket (Railway cron service, runs once and exits).
# Pinned to the production major version: Railway's Postgres is 18.7, and pg_dump must be at
# least as new as the server. postgres:18.7-bookworm ships pg_dump 18.7 (Debian 12).
FROM postgres:18.7-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-boto3 ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY services/backup/backup.py /app/backup.py
USER postgres
ENTRYPOINT []
CMD ["python3", "/app/backup.py"]
