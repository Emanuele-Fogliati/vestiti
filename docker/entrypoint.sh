#!/bin/sh
set -e
python -m app.cli migrate
if [ "${SEED_ON_START:-true}" = "true" ]; then
  python -m app.cli seed
fi
# Prices and stock of products with a readable shop page, at most once every
# PRICE_REFRESH_HOURS (0 = never). In the background: the app starts without waiting.
if [ "${PRICE_REFRESH_HOURS:-20}" != "0" ]; then
  python -m app.cli refresh-prices --hours "${PRICE_REFRESH_HOURS:-20}" >/dev/null 2>&1 &
fi
if [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PASSWORD" ]; then
  python -m app.cli create-admin --email "$ADMIN_EMAIL" --password "$ADMIN_PASSWORD"
fi
# Guests with no trips, idle for PRUNE_GUESTS_DAYS days, and expired email links are deleted
# at every start (0 = keep them). A failure here must not stop the app.
if [ "${PRUNE_GUESTS_DAYS:-30}" != "0" ]; then
  python -m app.cli prune-guests --days "${PRUNE_GUESTS_DAYS:-30}" || echo "prune-guests failed, continuing"
fi
# The same app on https too (port HTTPS_PORT, 0 = off): browsers allow the microphone (voice
# input) only on https or localhost, so a phone on the home network needs https. The certificate
# is made here once and kept in the certs volume; the browser warns the first time ("Advanced",
# "Proceed") because nobody signed it. For a real server use a proper reverse proxy instead.
HTTPS_PORT="${HTTPS_PORT:-8443}"
if [ "$HTTPS_PORT" != "0" ] && command -v openssl >/dev/null 2>&1; then
  CERTS=/app/certs
  if [ ! -s "$CERTS/cert.pem" ] || [ ! -s "$CERTS/key.pem" ]; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=vestiti local" \
      -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
      -keyout "$CERTS/key.pem" -out "$CERTS/cert.pem" >/dev/null 2>&1 \
      || echo "could not make the https certificate, https stays off"
  fi
  if [ -s "$CERTS/cert.pem" ]; then
    uvicorn app.main:app --host 0.0.0.0 --port "$HTTPS_PORT" \
      --ssl-keyfile "$CERTS/key.pem" --ssl-certfile "$CERTS/cert.pem" --workers 1 &
  fi
fi
# Trust X-Forwarded-For only from your reverse proxy: with "*" anyone could fake their IP
# and get around the login and AI rate limits. Behind a proxy, set FORWARDED_ALLOW_IPS to its IP.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers \
  --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
  --workers "${WEB_WORKERS:-2}"
