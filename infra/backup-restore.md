# Backups and restore (owner Q28: Option A, nightly pg_dump to an S3-compatible bucket)

## Why not Railway volume backups

The owner reports that Railway's scheduled volume backups / point-in-time recovery are Pro-plan
features; Railway's backup page does not name a plan, and a volume backup can only be restored into
the same project and environment, and wiping the volume deletes its backups
([volume backups](https://docs.railway.com/volumes/backups)). An off-site `pg_dump` in a bucket we
control survives all of that. **Option B** (upgrade to Pro and enable Daily/Weekly volume backups
on the Postgres volume) remains possible; the restore drill below works the same way for a
volume-restored database.

## What runs

- Railway service `backup` (`services/backup/Dockerfile`, `postgres:18.7-bookworm` + Python +
  boto3), **cron `30 7 * * *` UTC**, restart policy Never.
- `backup.py`: `pg_dump --format=custom --compress=9 --no-owner --no-privileges` of the production
  database → `edgefront/daily/edgefront-YYYYMMDDTHHMMSSZ.dump`; on Sundays also copied to
  `edgefront/weekly/…`. Keeps the newest **14 daily** and **8 weekly**; older objects are deleted.
  One JSON log line per step (`pg_dump done` with bytes/seconds, `uploaded`, `pruned`,
  `backup complete`); a failure logs `"level":"ERROR"` and exits 1 (visible in Railway).
- Expected size: the database is tens of MB in the first weeks (5 GB volume, 400-day METAR retention).

## Owner setup (one time)

**AWS S3** (the owner's choice, named in the Privacy Policy: bucket `edgefront-backups`, US-East):
1. S3 → Create bucket `edgefront-backups` in **US East (N. Virginia) `us-east-1`** (or Ohio
   `us-east-2`; the region in the endpoint and `BACKUP_S3_REGION` must be the bucket's). Keep
   **Block all public access** on. Objects are encrypted at rest (SSE-S3, the S3 default).
2. IAM → Users → create `edgefront-backup` (no console access) with an inline policy limited to the
   bucket: `s3:ListBucket` on `arn:aws:s3:::edgefront-backups` and `s3:PutObject`, `s3:GetObject`,
   `s3:DeleteObject` on `arn:aws:s3:::edgefront-backups/*`. Create an access key for it. For the
   restore drill, a second user with `s3:ListBucket` + `s3:GetObject` only.
3. In Railway → `backup` → Variables: `BACKUP_S3_ENDPOINT=https://s3.us-east-1.amazonaws.com`,
   `BACKUP_S3_BUCKET=edgefront-backups`, `BACKUP_S3_REGION=us-east-1`, the key pair, and
   `DATABASE_URL=${{Postgres.DATABASE_URL}}`. (With `BACKUP_S3_REGION` left at `auto` the job reads
   the region from an AWS endpoint.) Deploy, then **Run now** once and check the bucket.
4. GitHub → Settings → Secrets → Actions: the same `BACKUP_S3_*` values (the read-only key) for the
   restore drill.

Alternatively **Cloudflare R2** (no egress fees) or **Backblaze B2** (the Privacy Policy's provider
row would then have to change):
1. Create a **private** bucket, e.g. `edgefront-backups` (R2: R2 → Create bucket; B2: Buckets →
   Create, "Private"). Leave public access off. R2/B2 encrypt objects at rest.
2. Create an access key limited to that bucket with read/write/delete (R2: "Manage R2 API tokens" →
   Object Read & Write, this bucket only; B2: Application Keys → this bucket).
3. Optional (R2/B2 lifecycle rule): none needed, the job prunes itself.
4. In Railway → `backup` → Variables: `BACKUP_S3_ENDPOINT`, `BACKUP_S3_BUCKET`,
   `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY`, `BACKUP_S3_REGION` (`auto` for R2),
   `DATABASE_URL=${{Postgres.DATABASE_URL}}`. Deploy, then **Run now** once and check the bucket.
5. In GitHub → Settings → Secrets → Actions: the same five `BACKUP_S3_*` values (read-only key is
   enough there) so the restore drill can fetch backups.

## Restore drill (required once before go-live, then quarterly)

Run in GitHub Actions, never on a laptop (no local Postgres by owner rule):
**Actions → Restore drill → Run workflow → source = `bucket`**. The workflow
(`.github/workflows/restore-drill.yml`) starts a throwaway Postgres 18, downloads the newest daily
backup, runs `services/backup/restore_drill.sh` (pg_restore + checks) and writes the timings and
row counts to the job summary. `source = synthetic` proves the procedure without a bucket (builds a
database from migrations + seed, dumps it with the backup job's flags, restores it).

Record each drill here:

| Date (UTC) | Source | Backup object | Size | Fetch | Restore + checks | alembic_version | Rows (stations / metar_reports / model_values) | Result |
|---|---|---|---|---|---|---|---|---|
| *pending* | bucket | — | — | — | — | — | — | waiting for the first production backup |

## Restoring production for real

1. Railway → Postgres: create a **new** Postgres service (`Postgres-restore`) rather than wiping the
   old one. Download the chosen dump from the bucket.
2. From a Railway shell on the `backup` service (has pg_restore 17):
   `pg_restore --no-owner --no-privileges --exit-on-error --dbname="$RESTORE_URL" edgefront-….dump`
   with `RESTORE_URL` pointing at the new database (private URL).
3. Check with `services/backup/restore_drill.sh` (same checks), then point `api`, `worker` and
   `backup` at the new database (`DATABASE_URL=${{Postgres-restore.DATABASE_URL}}`) and deploy.
4. The worker refills the gap since the dump on its own (METAR backfill 36 h, CLI/DSM 3 days,
   forecasts and models on the next poll).
