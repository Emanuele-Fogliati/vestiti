#!/bin/sh
set -e
python -m app.cli migrate
if [ "${SEED_ON_START:-true}" = "true" ]; then
  python -m app.cli seed
fi
if [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PASSWORD" ]; then
  python -m app.cli create-admin --email "$ADMIN_EMAIL" --password "$ADMIN_PASSWORD"
fi
# Trust X-Forwarded-For only from your reverse proxy: with "*" anyone could fake their IP
# and get around the login and AI rate limits. Behind a proxy, set FORWARDED_ALLOW_IPS to its IP.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers \
  --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
  --workers "${WEB_WORKERS:-2}"
