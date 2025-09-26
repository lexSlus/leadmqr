# 🔐 Схема работы авторизации в LeadMQR

## 📁 Структура профилей

```
pw_profiles/
├── auth_setup/                    # Основной профиль (LeadProducer)
│   ├── Default/                   # Данные браузера Chrome
│   ├── Local State               # Состояние браузера
│   ├── SingletonLock             # Блокировка профиля
│   └── ... (другие файлы Chrome)
├── auth_setup_runner/             # Профиль для LeadRunner (синхронизируется)
│   ├── Default/                   # Копия данных браузера
│   ├── Local State               # Копия состояния
│   └── auth_state.json           # Дополнительное состояние
└── auth_state.json               # Общее состояние авторизации
```

## 🔄 Процесс синхронизации профилей

### 1. Настройка авторизации (setup_auth.py)
```
Пользователь запускает: python3 cli/setup_auth.py
    ↓
Открывается браузер с профилем: pw_profiles/auth_setup/
    ↓
Пользователь вводит логин/пароль Thumbtack
    ↓
Авторизация сохраняется в: pw_profiles/auth_setup/
    ↓
Состояние копируется в: pw_profiles/auth_state.json
```

### 2. Запуск LeadProducer
```
Docker Compose запускает: celery_lead_producer
    ↓
worker-entrypoint.sh выполняется
    ↓
TT_USER_DATA_DIR=/app/pw_profiles/auth_setup
    ↓
LeadProducer использует профиль: pw_profiles/auth_setup/
```

### 3. Запуск LeadRunner (celery_worker)
```
Docker Compose запускает: celery_worker
    ↓
worker-entrypoint.sh выполняется
    ↓
Проверка: команда содержит "lead_proc"?
    ↓
ДА → Автоматическая синхронизация:
    ↓
rsync -a /app/pw_profiles/auth_setup/ /app/pw_profiles/auth_setup_runner/
    ↓
cp /app/pw_profiles/auth_state.json /app/pw_profiles/auth_setup_runner/
    ↓
LeadRunner использует профиль: pw_profiles/auth_setup_runner/
```

## 🐳 Docker конфигурация

### LeadProducer (celery_lead_producer)
```yaml
environment:
  - TT_USER_DATA_DIR=/app/pw_profiles/auth_setup
volumes:
  - ./pw_profiles:/app/pw_profiles:rw
```

### LeadRunner (celery_worker)
```yaml
environment:
  - TT_USER_DATA_DIR=/app/pw_profiles/auth_setup  # Но entrypoint меняет на auth_setup_runner
volumes:
  - ./pw_profiles:/app/pw_profiles:rw
```

## 🔧 Worker Entrypoint логика

```bash
# 1. Очистка lock файлов
rm -f "/app/pw_profiles/auth_setup/Singleton"*
chown -R root:root "/app/pw_profiles/auth_setup"

# 2. Проверка команды
if echo "$@" | grep -q "lead_proc"; then
    # 3. Синхронизация для LeadRunner
    mkdir -p /app/pw_profiles/auth_setup_runner
    rm -rf /app/pw_profiles/auth_setup_runner/*
    
    # 4. Копирование профиля
    rsync -a /app/pw_profiles/auth_setup/ /app/pw_profiles/auth_setup_runner/ \
        --exclude="RunningChromeVersion*" \
        --exclude="SingletonLock*"
    
    # 5. Копирование состояния
    cp /app/pw_profiles/auth_state.json /app/pw_profiles/auth_setup_runner/
fi
```

## 📊 Переменные окружения

| Переменная | LeadProducer | LeadRunner | Описание |
|------------|--------------|------------|----------|
| `TT_USER_DATA_DIR` | `/app/pw_profiles/auth_setup` | `/app/pw_profiles/auth_setup` | Базовый путь к профилю |
| `TT_STATE_PATH` | `/app/.data/.tt_state.json` | `/app/.data/.tt_state.json` | Путь к состоянию |
| `TT_HEADLESS` | `false` | `false` | Режим браузера |
| `TT_LOCALE` | `en-US` | `en-US` | Локаль |
| `TT_TIMEZONE_ID` | `America/New_York` | `America/New_York` | Часовой пояс |

## 🚨 Важные моменты

### 1. Блокировка профилей
- **SingletonLock** файлы предотвращают одновременное использование профиля
- Entrypoint очищает эти файлы при запуске
- Каждый сервис использует свой профиль

### 2. Синхронизация
- **LeadProducer** использует оригинальный профиль `auth_setup/`
- **LeadRunner** использует копию `auth_setup_runner/`
- Синхронизация происходит автоматически при запуске LeadRunner

### 3. Права доступа
- Профили монтируются с правами `rw` (read-write)
- Entrypoint устанавливает правильные права доступа
- Пользователь 1000:1000 для работы с профилями

### 4. Исключения при копировании
- `RunningChromeVersion*` - версия браузера
- `SingletonLock*` - файлы блокировки
- Эти файлы не копируются, чтобы избежать конфликтов

## 🔍 Диагностика

### Проверка профилей
```bash
# Проверка структуры
ls -la pw_profiles/

# Проверка синхронизации
ls -la pw_profiles/auth_setup_runner/

# Проверка состояния
cat pw_profiles/auth_state.json
```

### Проверка в контейнерах
```bash
# Проверка LeadProducer
docker-compose exec celery_lead_producer ls -la /app/pw_profiles/auth_setup/

# Проверка LeadRunner
docker-compose exec celery_worker ls -la /app/pw_profiles/auth_setup_runner/
```

### Очистка профилей
```bash
# Очистка через Django команду
docker-compose exec celery_lead_producer python manage.py clear_profiles

# Ручная очистка
rm -rf pw_profiles/auth_setup/*
rm -rf pw_profiles/auth_setup_runner/*
```

## 🎯 Результат

Благодаря этой системе:
- **LeadProducer** и **LeadRunner** работают независимо
- Авторизация сохраняется между перезапусками
- Нет конфликтов при одновременной работе
- Автоматическая синхронизация профилей
- Простая диагностика и отладка
