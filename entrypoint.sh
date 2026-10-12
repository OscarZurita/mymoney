#!/bin/sh
set -e

# Postgres readiness is guaranteed by the compose healthcheck (see
# depends_on: condition: service_healthy), so migrations can run right away.
echo "==> Applying database migrations"
python manage.py migrate --noinput

# WhiteNoise serves the app's static files out of STATIC_ROOT, so they have to
# be collected there first. Under the dev override DEBUG is on and Django's
# staticfiles finders serve straight from the source tree instead, making the
# collected copy dead weight -- and a needless write into the bind mount on
# every start. DEBUG reaches us as a real environment variable only in that
# dev override; in the default (always-on) mode it is unset here and read from
# .env by Django itself, so an empty value correctly means "collect".
case "$(printf '%s' "${DEBUG:-}" | tr '[:upper:]' '[:lower:]')" in
  true|1|yes|on)
    echo "==> DEBUG is on, skipping collectstatic"
    ;;
  *)
    echo "==> Collecting static files"
    python manage.py collectstatic --noinput
    ;;
esac

echo "==> Starting: $*"
exec "$@"
