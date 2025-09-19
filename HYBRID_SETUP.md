# 🚀 Гибридная архитектура LeadMQR

## 📋 Что запускать

### 1. Docker Compose (сервисы)
```bash
docker-compose -f docker-compose-dev.yaml up -d
```

### 2. Локальный Lead Producer (Playwright)
```bash
python start_local_producer.py
```

## 🔧 Архитектура

**В Docker Compose:**
- ✅ PostgreSQL (база данных)
- ✅ Redis (кеш, rate limiting)
- ✅ RabbitMQ (очереди Celery)
- ✅ Django Web Server
- ✅ Celery Beat (планировщик)
- ✅ Celery AI Worker (только AI звонки)

**Локально на Mac:**
- ✅ Playwright с persistent context
- ✅ Chrome браузер для отладки
- ✅ Lead Producer (поиск и обработка лидов)

## 🎯 Преимущества

- **Отладка**: `chrome://inspect` для Playwright
- **Скорость**: Persistent context - браузер не закрывается
- **Гибкость**: Локальный Playwright + Docker сервисы
- **Масштабируемость**: Celery workers в Docker

## 🔍 Отладка

1. Запустите Docker Compose
2. Запустите локальный producer
3. Откройте `chrome://inspect` для отладки Playwright
4. Debug порт: `http://localhost:9222`
5. Логи: `docker-compose logs -f celery_worker_ai`

## 🛑 Остановка

```bash
# Остановить Docker
docker-compose -f docker-compose-dev.yaml down

# Остановить локальный producer
Ctrl+C в терминале с producer
```
