#!/bin/sh
set -e
python -m app.cli migrate
if [ "${SEED_ON_START:-true}" = "true" ]; then
  python -m app.cli seed
fi
if [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PASSWORD" ]; then
  python -m app.cli create-admin --email "$ADMIN_EMAIL" --password "$ADMIN_PASSWORD"
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*" \
  --workers "${WEB_WORKERS:-2}"
