#!/bin/sh
set -e

python manage.py migrate --noinput 2>/dev/null || true
python manage.py collectstatic --noinput 2>/dev/null || true

exec "$@"