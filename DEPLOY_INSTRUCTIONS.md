# 🚀 Инструкции по деплою LeadMQR на Ubuntu

## 📋 Подготовка к деплою

### 1. Файлы для загрузки на сервер

Создайте на Ubuntu сервере директорию проекта и загрузите следующие файлы:

```bash
# Создайте директорию проекта
mkdir -p /opt/leadmqr
cd /opt/leadmqr
```

### 2. Основные файлы проекта

```bash
# Основные конфигурационные файлы
requirements.txt
docker-compose-dev.yaml
Dockerfile.base
entrypoint.sh
manage.py

# Docker файлы
docker/celery/Dockerfile.celery_worker
docker/celery/worker-entrypoint.sh
docker/playwright/Dockerfile

# Django проект
leadmqr/__init__.py
leadmqr/settings.py
leadmqr/urls.py
leadmqr/wsgi.py
leadmqr/asgi.py
leadmqr/celery.py

# Django приложения
leads/ (вся папка)
ai_calls/ (вся папка)
telegram_app/ (вся папка)

# Playwright Bot (основная логика)
playwright_bot/ (вся папка)

# Вспомогательные файлы
get_chat_id.py
fix_runner_profile.sh
rebuild_docker.sh
start_docker_with_fix.sh

# CLI утилиты для настройки авторизации
cli/setup_auth.py
cli/setup_auth.sh
cli/run_lead_producer.py
cli/run_lead_runner.py
cli/run_single_pass.py
cli/test_lead_producer.py
cli/test_lead_runner.py
cli/debug_phone_extraction.py
cli/debug_phone.py
cli/README.md

# Профили Playwright (КРИТИЧЕСКИ ВАЖНО!)
pw_profiles/ (вся папка)
pw_profiles_runner/ (вся папка)
```

### 3. Создание .env файла

Создайте файл `.env` в корне проекта:

```bash
# Django
DJANGO_SECRET_KEY=your_very_secret_key_here
DEBUG=False
ALLOWED_HOSTS=your_domain.com,localhost,127.0.0.1

# Database
POSTGRES_DB=leadmqr
POSTGRES_USER=leadmqr_user
POSTGRES_PASSWORD=your_strong_db_password
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# RabbitMQ
RABBITMQ_USER=guest
RABBITMQ_PASS=guest

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# AI/Voice (если используется)
VOCALAI_API_KEY=your_api_key_here
AGENT_ID=your_agent_id_here
FROM_PHONE_NUMBER=your_phone_number

# Thumbtack
THUMBTACK_EMAIL=your_thumbtack_email
THUMBTACK_PASSWORD=your_thumbtack_password
```

## 🐳 Установка и запуск

### 1. Установка Docker и Docker Compose

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Перезагрузка для применения изменений группы
sudo reboot
```

### 2. Запуск системы

```bash
cd /opt/leadmqr

# Сборка и запуск всех сервисов
docker-compose -f docker-compose-dev.yaml up --build -d

# Проверка статуса
docker-compose -f docker-compose-dev.yaml ps

# Просмотр логов
docker-compose -f docker-compose-dev.yaml logs -f
```

### 3. Первоначальная настройка

```bash
# Выполнение миграций БД
docker-compose -f docker-compose-dev.yaml exec web python manage.py migrate

# Создание суперпользователя (опционально)
docker-compose -f docker-compose-dev.yaml exec web python manage.py createsuperuser

# Настройка профиля Thumbtack (ВАЖНО!)
# Вариант 1: Через Django команду (в контейнере)
docker-compose -f docker-compose-dev.yaml exec celery_lead_producer python manage.py setup_thumbtack_profile

# Вариант 2: Через CLI утилиту (на хосте)
python3 cli/setup_auth.py

# Вариант 3: Через bash скрипт (на хосте)
bash cli/setup_auth.sh
```

## 🔧 Управление системой

### Основные команды

```bash
# Запуск системы
docker-compose -f docker-compose-dev.yaml up -d

# Остановка системы
docker-compose -f docker-compose-dev.yaml down

# Перезапуск конкретного сервиса
docker-compose -f docker-compose-dev.yaml restart celery_worker

# Просмотр логов
docker-compose -f docker-compose-dev.yaml logs -f celery_worker
docker-compose -f docker-compose-dev.yaml logs -f celery_lead_producer

# Пересборка образов
docker-compose -f docker-compose-dev.yaml build --no-cache
```

### Мониторинг

```bash
# Статус всех контейнеров
docker-compose -f docker-compose-dev.yaml ps

# Использование ресурсов
docker stats

# Логи в реальном времени
docker-compose -f docker-compose-dev.yaml logs -f --tail=100
```

## 🔐 Настройка авторизации Thumbtack

### Варианты настройки авторизации:

#### Вариант 1: Через CLI утилиту (рекомендуется)
```bash
# Запуск интерактивной настройки авторизации
python3 cli/setup_auth.py

# Или через bash скрипт
bash cli/setup_auth.sh
```

**Процесс:**
1. Откроется браузер
2. Введите логин и пароль Thumbtack
3. Решите капчу если появится
4. Нажмите Enter в консоли после успешного входа
5. Авторизация сохранится в `pw_profiles/auth_setup/`

#### Вариант 2: Через Django команду
```bash
# В контейнере
docker-compose -f docker-compose-dev.yaml exec celery_lead_producer python manage.py setup_thumbtack_profile
```

#### Вариант 3: Ручная настройка
```bash
# Очистка старых профилей
docker-compose -f docker-compose-dev.yaml exec celery_lead_producer python manage.py clear_profiles

# Затем настройка нового профиля
python3 cli/setup_auth.py
```

### Структура профилей:
- `pw_profiles/auth_setup/` - основной профиль для LeadProducer
- `pw_profiles/auth_setup_runner/` - профиль для LeadRunner (синхронизируется автоматически)
- `pw_profiles/auth_state.json` - состояние авторизации

## 🚨 Важные замечания

### 1. Профили Playwright
- **КРИТИЧЕСКИ ВАЖНО**: Папка `pw_profiles/` содержит аутентификацию Thumbtack
- Без неё система не сможет войти в аккаунт
- Убедитесь, что профили скопированы полностью
- Профили автоматически синхронизируются между LeadProducer и LeadRunner

### 2. Переменные окружения
- Обязательно настройте все переменные в `.env`
- Особенно важны `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`
- `THUMBTACK_EMAIL` и `THUMBTACK_PASSWORD` для входа в аккаунт

### 3. Сеть и порты
- Система использует порты: 8000 (web), 5432 (postgres), 6379 (redis), 5672 (rabbitmq)
- Убедитесь, что порты свободны или измените их в `docker-compose-dev.yaml`

### 4. Ресурсы
- Система требует минимум 2GB RAM
- Playwright использует много ресурсов для браузера
- Рекомендуется 4GB+ RAM для стабильной работы

## 🧪 Тестирование системы

### Тестирование компонентов:

```bash
# Тестирование LeadProducer
python3 cli/test_lead_producer.py

# Тестирование LeadRunner
python3 cli/test_lead_runner.py

# Тестирование извлечения телефонов
python3 cli/debug_phone_extraction.py

# Запуск одного цикла обработки
python3 cli/run_single_pass.py
```

### Проверка авторизации:
```bash
# Проверка профиля Thumbtack
python3 cli/setup_auth.py --headless

# Очистка и пересоздание профиля
docker-compose -f docker-compose-dev.yaml exec celery_lead_producer python manage.py clear_profiles
python3 cli/setup_auth.py
```

## 🔍 Диагностика проблем

### Проверка логов
```bash
# Логи всех сервисов
docker-compose -f docker-compose-dev.yaml logs

# Логи конкретного сервиса
docker-compose -f docker-compose-dev.yaml logs celery_worker
docker-compose -f docker-compose-dev.yaml logs celery_lead_producer
```

### Проверка подключений
```bash
# Проверка БД
docker-compose -f docker-compose-dev.yaml exec db psql -U leadmqr_user -d leadmqr -c "SELECT 1;"

# Проверка Redis
docker-compose -f docker-compose-dev.yaml exec redis redis-cli ping

# Проверка RabbitMQ
docker-compose -f docker-compose-dev.yaml exec rabbitmq rabbitmq-diagnostics ping
```

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи всех сервисов
2. Убедитесь, что все переменные окружения настроены
3. Проверьте, что профили Playwright скопированы корректно
4. Убедитесь, что все порты свободны

Система готова к работе! 🎉
