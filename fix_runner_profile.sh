#!/bin/bash

echo "🔧 Fixing LeadRunner profile after Docker restart..."

# Проверяем, что мы в правильной директории
if [ ! -d "pw_profiles" ]; then
    echo "❌ Error: pw_profiles directory not found. Please run this script from the project root."
    exit 1
fi

# Проверяем, что Docker контейнеры запущены
if ! docker ps | grep -q "leadmqr_celery_worker"; then
    echo "❌ Error: leadmqr_celery_worker container is not running. Please start Docker containers first."
    exit 1
fi

echo "📁 Cleaning old LeadRunner profile..."
# Очищаем старый профиль
rm -rf pw_profiles/auth_setup_runner_shared/*

echo "📋 Copying fresh profile from auth_setup..."
# Копируем свежий профиль
rsync -av pw_profiles/auth_setup/ pw_profiles/auth_setup_runner_shared/ --exclude="RunningChromeVersion*" --exclude="SingletonLock*"

echo "🔄 Restarting Celery worker..."
# Перезапускаем Celery worker
docker restart leadmqr_celery_worker

echo "⏳ Waiting for Celery worker to start..."
# Ждем, пока воркер запустится
sleep 5

echo "✅ LeadRunner profile fixed and Celery worker restarted!"
echo "🎯 You can now check logs with: docker logs leadmqr_celery_worker --tail 10"
