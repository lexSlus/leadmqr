#!/bin/sh
set -e
## гарантируем, что профиль доступен пользователю процесса (часто uid=1000)
chown -R 1000:1000 /app/playwright_profile 2>/dev/null || true
chmod 700 /app/playwright_profile 2>/dev/null || true

python manage.py migrate --noinput 2>/dev/null || true
python manage.py collectstatic --noinput 2>/dev/null || true

exec "$@"