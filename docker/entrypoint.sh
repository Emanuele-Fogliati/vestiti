#!/bin/sh
set -e
python -m app.cli migrate
if [ "${SEED_ON_START:-true}" = "true" ]; then
  python -m app.cli seed
fi
if [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PASSWORD" ]; then
  python -m app.cli create-admin --email "$ADMIN_EMAIL" --password "$ADMIN_PASSWORD"
fi
# Guests with no trips, idle for PRUNE_GUESTS_DAYS days, and expired email links are deleted
# at every start (0 = keep them). A failure here must not stop the app.
if [ "${PRUNE_GUESTS_DAYS:-30}" != "0" ]; then
  python -m app.cli prune-guests --days "${PRUNE_GUESTS_DAYS:-30}" || echo "prune-guests failed, continuing"
fi
# Trust X-Forwarded-For only from your reverse proxy: with "*" anyone could fake their IP
# and get around the login and AI rate limits. Behind a proxy, set FORWARDED_ALLOW_IPS to its IP.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers \
  --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
  --workers "${WEB_WORKERS:-2}"
