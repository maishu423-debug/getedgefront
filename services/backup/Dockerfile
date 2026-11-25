# Build context: repository root.  docker build -f services/backup/Dockerfile .
# Nightly pg_dump → S3-compatible bucket (Railway cron service, runs once and exits).
# postgres:17 provides pg_dump 17, which can dump Postgres 17 and older servers.
FROM postgres:17.12-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-boto3 ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY services/backup/backup.py /app/backup.py
USER postgres
ENTRYPOINT []
CMD ["python3", "/app/backup.py"]
