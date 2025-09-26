#!/bin/bash

# Скрипт для принудительной пересборки Docker контейнеров с новым кодом

echo "🔄 Принудительная пересборка Docker контейнеров..."

# Устанавливаем BUILD_DATE для принудительного обновления кода
export BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')

echo "📅 Build date: $BUILD_DATE"

# Останавливаем контейнеры
echo "⏹️  Останавливаем контейнеры..."
docker-compose -f docker-compose-dev.yaml down

# Удаляем образы для принудительной пересборки
echo "🗑️  Удаляем старые образы..."
docker-compose -f docker-compose-dev.yaml build --no-cache

# Запускаем контейнеры
echo "🚀 Запускаем контейнеры..."
docker-compose -f docker-compose-dev.yaml up -d

echo "✅ Пересборка завершена!"
echo "📊 Статус контейнеров:"
docker-compose -f docker-compose-dev.yaml ps

