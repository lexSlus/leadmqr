#!/bin/bash

echo "🚀 Starting Docker with automatic LeadRunner profile fix..."

# Останавливаем контейнеры
echo "🛑 Stopping Docker containers..."
docker-compose -f docker-compose-dev.yaml down

# Запускаем контейнеры
echo "▶️ Starting Docker containers..."
docker-compose -f docker-compose-dev.yaml up -d

# Ждем, пока контейнеры запустятся
echo "⏳ Waiting for containers to start..."
sleep 10

# Автоматически исправляем профиль
echo "🔧 Auto-fixing LeadRunner profile..."
./fix_runner_profile.sh

echo "✅ Docker started with automatic profile fix!"
echo "🎯 Check logs with: docker logs leadmqr_celery_worker --tail 10"
