#!/usr/bin/env sh
set -e

# На всякий: чистим зависшие лок-файлы профиля, чтобы не словить SingletonLock
if [ -n "$TT_USER_DATA_DIR" ] && [ -d "$TT_USER_DATA_DIR" ]; then
  rm -f "$TT_USER_DATA_DIR/Singleton"* 2>/dev/null || true
  chown -R 1000:1000 "$TT_USER_DATA_DIR" 2>/dev/null || true
  chmod 700 "$TT_USER_DATA_DIR" 2>/dev/null || true
fi

# Автоматически синхронизируем профиль LeadRunner с LeadProducer
if echo "$@" | grep -q "lead_proc"; then
  echo "🔧 Auto-syncing LeadRunner profile in entrypoint..."
  
  # Создаем директорию если не существует
  mkdir -p /app/pw_profiles/auth_setup_runner
  
  # Очищаем старый профиль
  rm -rf /app/pw_profiles/auth_setup_runner/*
  
  # Копируем свежий профиль
  if [ -d "/app/pw_profiles/auth_setup" ]; then
    rsync -a /app/pw_profiles/auth_setup/ /app/pw_profiles/auth_setup_runner/ --exclude="RunningChromeVersion*" --exclude="SingletonLock*" 2>/dev/null || true
    # Также копируем auth_state.json если он есть
    if [ -f "/app/pw_profiles/auth_state.json" ]; then
      cp /app/pw_profiles/auth_state.json /app/pw_profiles/auth_setup_runner/ 2>/dev/null || true
    fi
    echo "✅ LeadRunner profile auto-synced in entrypoint!"
  else
    echo "⚠️ Warning: auth_setup profile not found, LeadRunner may need manual login"
  fi
fi

# Не запускаем тут миграции — это делает web/beat (или ваш общий entrypoint)
exec "$@"