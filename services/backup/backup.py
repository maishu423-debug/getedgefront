"""Nightly Postgres backup to an S3-compatible bucket (owner Q28: Option A).

Runs once and exits (Railway cron service). Steps:
1. `pg_dump --format=custom --compress=9` of DATABASE_URL into a temp file.
2. Upload as `<prefix>daily/edgefront-YYYYMMDDTHHMMSSZ.dump`; on Sundays (UTC) also as
   `<prefix>weekly/…`.
3. Keep the newest 14 daily and 8 weekly objects; delete older ones.
Every step logs one JSON line (Railway log view). The bucket must be private; AWS S3, R2 and B2
encrypt objects at rest (S3: SSE-S3 by default since January 2023).

Environment (all secrets except the prefix/region):
  DATABASE_URL                 postgresql://… (Railway reference to the Postgres service)
  BACKUP_S3_ENDPOINT           AWS S3 (owner's choice): https://s3.us-east-1.amazonaws.com; also
                               https://<account>.r2.cloudflarestorage.com or
                               https://s3.<region>.backblazeb2.com
  BACKUP_S3_BUCKET             bucket name
  BACKUP_S3_ACCESS_KEY_ID      bucket-scoped key
  BACKUP_S3_SECRET_ACCESS_KEY
  BACKUP_S3_REGION             the bucket's region (us-east-1); "auto" for R2 (default auto: on
                               AWS the region is then read from the endpoint)
  BACKUP_PREFIX                default "edgefront/"
  BACKUP_KEEP_DAILY / BACKUP_KEEP_WEEKLY   default 14 / 8
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def log(msg: str, level: str = "INFO", **extra: object) -> None:
    rec = {"ts": datetime.now(UTC).isoformat(), "level": level, "logger": "edgefront.backup",
           "msg": msg, "source": "backup", **extra}  # fmt: skip
    print(json.dumps(rec, default=str), flush=True)


def pg_url(url: str) -> str:
    """pg_dump wants libpq's scheme, not SQLAlchemy's driver-qualified one."""
    for prefix in ("postgresql+psycopg://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


def s3_region(endpoint: str, region: str) -> str:
    """AWS signs requests per region, so "auto" (R2's value) is replaced by the region in an AWS
    endpoint (https://s3.us-east-1.amazonaws.com or https://s3-us-east-1.amazonaws.com)."""
    m = re.match(r"https://s3[.-]([a-z0-9-]+)\.amazonaws\.com/?$", endpoint)
    return m.group(1) if region == "auto" and m else region


def s3_client() -> Any:  # boto3 has no type stubs in the image
    import boto3  # from Debian's python3-boto3 in the image

    return boto3.client(
        "s3",
        endpoint_url=os.environ["BACKUP_S3_ENDPOINT"],
        aws_access_key_id=os.environ["BACKUP_S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["BACKUP_S3_SECRET_ACCESS_KEY"],
        region_name=s3_region(
            os.environ["BACKUP_S3_ENDPOINT"], os.environ.get("BACKUP_S3_REGION", "auto")
        ),
    )


def prune(s3: Any, bucket: str, prefix: str, keep: int) -> list[str]:
    keys: list[str] = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys += [o["Key"] for o in page.get("Contents", [])]
    doomed = sorted(keys, reverse=True)[keep:]  # names sort by timestamp
    for k in doomed:
        s3.delete_object(Bucket=bucket, Key=k)
    return doomed


def main() -> int:
    t0 = time.monotonic()
    now = datetime.now(UTC)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    prefix = os.environ.get("BACKUP_PREFIX", "edgefront/")
    bucket = os.environ["BACKUP_S3_BUCKET"]
    keep_daily = int(os.environ.get("BACKUP_KEEP_DAILY", "14"))
    keep_weekly = int(os.environ.get("BACKUP_KEEP_WEEKLY", "8"))
    try:
        with tempfile.TemporaryDirectory() as d:
            dump = Path(d) / f"edgefront-{stamp}.dump"
            t = time.monotonic()
            pg_dump = shutil.which("pg_dump") or "/usr/bin/pg_dump"
            subprocess.run(  # noqa: S603 - fixed argv, no shell
                [pg_dump, "--format=custom", "--compress=9", "--no-owner", "--no-privileges",
                 f"--file={dump}", f"--dbname={pg_url(os.environ['DATABASE_URL'])}"],
                check=True, capture_output=True, text=True,
            )  # fmt: skip
            size = dump.stat().st_size
            log("pg_dump done", bytes=size, seconds=round(time.monotonic() - t, 1))
            s3 = s3_client()
            t = time.monotonic()
            daily_key = f"{prefix}daily/edgefront-{stamp}.dump"
            s3.upload_file(str(dump), bucket, daily_key)
            uploaded = [daily_key]
            if now.weekday() == 6:  # Sunday (UTC)
                weekly_key = f"{prefix}weekly/edgefront-{stamp}.dump"
                s3.copy_object(Bucket=bucket, Key=weekly_key,
                               CopySource={"Bucket": bucket, "Key": daily_key})  # fmt: skip
                uploaded.append(weekly_key)
            log("uploaded", keys=uploaded, seconds=round(time.monotonic() - t, 1))
            gone = prune(s3, bucket, f"{prefix}daily/", keep_daily)
            gone += prune(s3, bucket, f"{prefix}weekly/", keep_weekly)
            log("pruned", deleted=gone)
    except subprocess.CalledProcessError as e:
        log("pg_dump failed", level="ERROR", returncode=e.returncode, stderr=e.stderr[-2000:])
        return 1
    except Exception as e:
        log("backup failed", level="ERROR", error=f"{type(e).__name__}: {e}")
        return 1
    log("backup complete", seconds=round(time.monotonic() - t0, 1), bytes=size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
