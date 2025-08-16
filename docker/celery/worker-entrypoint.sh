#!/usr/bin/env sh
set -e

# На всякий: чистим зависшие лок-файлы профиля, чтобы не словить SingletonLock
if [ -n "$TT_USER_DATA_DIR" ] && [ -d "$TT_USER_DATA_DIR" ]; then
  rm -f "$TT_USER_DATA_DIR/Singleton"* 2>/dev/null || true
  chown -R 1000:1000 "$TT_USER_DATA_DIR" 2>/dev/null || true
  chmod 700 "$TT_USER_DATA_DIR" 2>/dev/null || true
fi

# Не запускаем тут миграции — это делает web/beat (или ваш общий entrypoint)
exec "$@"