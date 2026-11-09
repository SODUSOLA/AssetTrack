#!/usr/bin/env bash
# Run the browser tests against the real API and a throwaway database.
#
#   scripts/e2e.sh                 # all journeys, Chrome
#   scripts/e2e.sh e2e/auth.spec.ts
#
# Run it from anywhere; it works out the repository root itself. PYTHON may be "poetry run python"
# (it is run inside backend/). Needs: the db container (docker compose up -d db), a built app
# (cd frontend && npm run build), and Chrome installed (or E2E_BUNDLED=1 after
# `npx playwright install chromium`).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${E2E_PORT:-8002}"
DB="audit_e2e"
export DEMO_PASSWORD="${E2E_PASSWORD:-e2e-Password-123}"
export E2E_PASSWORD="$DEMO_PASSWORD"
export E2E_BASE_URL="http://localhost:${PORT}"
export DATABASE_URL="${E2E_DATABASE_URL:-postgresql+psycopg://audit:audit@localhost:5432/${DB}}"
PY="${PYTHON:-$ROOT/backend/.venv/bin/python}"

echo "Preparing database ${DB}"
SQL=(-q -c "DROP DATABASE IF EXISTS ${DB} WITH (FORCE)" -c "CREATE DATABASE ${DB}")
if command -v docker >/dev/null 2>&1 && [ -n "$(docker compose ps -q db 2>/dev/null)" ]; then
  docker compose exec -T db psql -U audit -d postgres "${SQL[@]}"
else # CI: Postgres is a service container on localhost
  PGPASSWORD=audit psql -h localhost -U audit -d postgres "${SQL[@]}"
fi
(cd backend && $PY -m alembic upgrade head >/dev/null && $PY -m scripts.seed_demo >/dev/null)

echo "Starting the API on :${PORT}"
# --proxy-headers lets each test sign in from its own forwarded address, so the 5-a-minute
# sign-in limit does not trip the suite. It is for this test server only.
(cd backend && exec $PY -m uvicorn app.main:app --port "$PORT" --proxy-headers \
  --forwarded-allow-ips='*') >/tmp/lasrra-e2e-api.log 2>&1 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT
for _ in $(seq 1 40); do
  curl -sf "http://localhost:${PORT}/health" >/dev/null && break
  sleep 0.5
done
curl -sf "http://localhost:${PORT}/health" >/dev/null || { echo "API did not start; see /tmp/lasrra-e2e-api.log"; exit 1; }

cd frontend
npx playwright test "$@"
