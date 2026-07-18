#!/bin/sh
set -e

# Postgres readiness is guaranteed by the compose healthcheck (see
# depends_on: condition: service_healthy), so migrations can run right away.
echo "==> Applying database migrations"
python manage.py migrate --noinput

echo "==> Starting: $*"
exec "$@"
