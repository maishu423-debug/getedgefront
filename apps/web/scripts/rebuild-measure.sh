#!/usr/bin/env bash
# Dev helper (Windows/Git Bash): stop the web server on :3000, rebuild, start it in the
# background against the local API on :8000, then run Lighthouse via scripts/lh.mjs.
#   bash scripts/rebuild-measure.sh <outDir> <runs> <path> [path ...]
set -e
cd "$(dirname "$0")/.."
powershell -NoProfile -Command 'Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }' || true
pnpm build < /dev/null > /tmp/build.log 2>&1 || { tail -20 /tmp/build.log; exit 1; }
(API_INTERNAL_URL=http://127.0.0.1:8000 nohup pnpm start -p 3000 > /tmp/web.log 2>&1 &)
for _ in $(seq 1 60); do curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/ | grep -q 200 && break; sleep 1; done
OUT=$1
RUNS=$2
shift 2
mkdir -p "$OUT"
URLS=()
for p in "$@"; do
  curl -s -o /dev/null "http://localhost:3000$p"
  URLS+=("http://localhost:3000$p")
done
MSYS_NO_PATHCONV=1 node scripts/lh.mjs "$OUT" "$RUNS" "${URLS[@]}" 2>&1 | grep -v "DEP0190\|trace-deprecation"
