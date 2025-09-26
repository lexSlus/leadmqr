# ✅ Финальный чеклист для деплоя на Ubuntu

## 📦 Файлы для загрузки на сервер

### 🏗️ Основные конфигурационные файлы
- [ ] `requirements.txt`
- [ ] `docker-compose-dev.yaml`
- [ ] `Dockerfile.base`
- [ ] `entrypoint.sh`
- [ ] `manage.py`

### 🐳 Docker файлы
- [ ] `docker/celery/Dockerfile.celery_worker`
- [ ] `docker/celery/worker-entrypoint.sh`
- [ ] `docker/playwright/Dockerfile`

### 🐍 Python код
- [ ] `leadmqr/` (вся папка)
- [ ] `leads/` (вся папка)
- [ ] `ai_calls/` (вся папка)
- [ ] `telegram_app/` (вся папка)
- [ ] `playwright_bot/` (вся папка)

### 🔧 CLI утилиты
- [ ] `cli/` (вся папка)
- [ ] `get_chat_id.py`
- [ ] `fix_runner_profile.sh`
- [ ] `rebuild_docker.sh`
- [ ] `start_docker_with_fix.sh`

### 🔐 Профили Playwright (КРИТИЧЕСКИ ВАЖНО!)
- [ ] `pw_profiles/` (вся папка)
- [ ] `pw_profiles_runner/` (вся папка)

### 📚 Документация
- [ ] `DEPLOY_INSTRUCTIONS.md`
- [ ] `QUICK_DEPLOY.md`
- [ ] `AUTH_FLOW.md`
- [ ] `deploy_files.txt`

## ⚙️ Настройка на сервере

### 1. Создание .env файла
```bash
cat > .env << EOF
DJANGO_SECRET_KEY=your_secret_key_here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1

POSTGRES_DB=leadmqr
POSTGRES_USER=leadmqr_user
POSTGRES_PASSWORD=your_db_password
POSTGRES_HOST=db
POSTGRES_PORT=5432

REDIS_HOST=redis
REDIS_PORT=6379

RABBITMQ_USER=guest
RABBITMQ_PASS=guest

TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

THUMBTACK_EMAIL=your_email
THUMBTACK_PASSWORD=your_password
EOF
```

### 2. Установка Docker
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
sudo reboot
```

### 3. Установка Docker Compose
```bash
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 4. Запуск системы
```bash
docker-compose -f docker-compose-dev.yaml up --build -d
```

### 5. Настройка авторизации
```bash
python3 cli/setup_auth.py
```

## 🔍 Проверка работы

### Статус контейнеров
```bash
docker-compose -f docker-compose-dev.yaml ps
```

### Логи
```bash
docker-compose -f docker-compose-dev.yaml logs -f
```

### Тестирование
```bash
python3 cli/test_lead_producer.py
```

## 🚨 Критически важно

1. **Профили Playwright** - без них система не работает
2. **Переменные .env** - настройте все обязательные
3. **Авторизация Thumbtack** - настройте через setup_auth
4. **Ресурсы** - минимум 2GB RAM, рекомендуется 4GB+

## 📞 При проблемах

1. Проверьте логи: `docker-compose logs -f`
2. Проверьте профили: `ls -la pw_profiles/`
3. Очистите профили: `python manage.py clear_profiles`
4. Пересоздайте авторизацию: `python3 cli/setup_auth.py`

## 🎯 Готово!

После выполнения всех пунктов система будет работать точно так же, как на вашем локальном компьютере:
- ✅ LeadProducer найдет новые лиды
- ✅ LeadRunner обработает лиды и найдет телефоны
- ✅ Telegram уведомления отправятся на английском с Miami timezone
- ✅ Все этапы обработки пройдут успешно

Удачи с деплоем! 🚀
