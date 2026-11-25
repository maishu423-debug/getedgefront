#!/usr/bin/env bash
# Restore drill: restore a pg_dump custom-format file into a throwaway database and check it.
#   RESTORE_URL=postgresql://user:pass@host:5432/drill bash services/backup/restore_drill.sh <dump>
# Prints one timing line per step and the row counts that prove the restore worked.
set -euo pipefail
DUMP=$1
: "${RESTORE_URL:?set RESTORE_URL to a throwaway database}"
t0=$(date +%s)
echo "dump: $(du -h "$DUMP" | cut -f1)  $DUMP"
pg_restore --list "$DUMP" > /dev/null && echo "archive readable: ok"
t=$(date +%s)
pg_restore --no-owner --no-privileges --exit-on-error --jobs=2 --dbname="$RESTORE_URL" "$DUMP"
echo "pg_restore: $(( $(date +%s) - t )) s"
psql "$RESTORE_URL" -v ON_ERROR_STOP=1 -At <<'SQL'
SELECT 'alembic_version ' || version_num FROM alembic_version;
SELECT 'stations ' || count(*) FROM stations;
SELECT 'metar_reports ' || count(*) || ' newest ' || coalesce(max(observed_at)::text, '-') FROM metar_reports;
SELECT 'cli_products ' || count(*) FROM cli_products;
SELECT 'dsm_products ' || count(*) FROM dsm_products;
SELECT 'nws_forecasts ' || count(*) FROM nws_forecasts;
SELECT 'model_runs ' || count(*) FROM model_runs;
SELECT 'model_values ' || count(*) FROM model_values;
SELECT 'db_size ' || pg_size_pretty(pg_database_size(current_database()));
SQL
echo "total: $(( $(date +%s) - t0 )) s"
