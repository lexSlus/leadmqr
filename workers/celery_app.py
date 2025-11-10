# celery_app.py
"""
Настройка Celery для "Рабочих".
Использует gevent пул. WebSocket операции выполняются через asyncio.run().
"""
import gevent.monkey
gevent.monkey.patch_all(ssl=False)  # Не патчим SSL, чтобы избежать конфликта с requests/urllib3

from celery import Celery
from celery.schedules import crontab
from config import CONFIG

# Создаем Celery приложение
celery_app = Celery(
    "workers",
    broker=CONFIG.celery_broker_url,
    backend=CONFIG.celery_result_backend,
)

# Конфигурация Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Для асинхронных операций
    task_always_eager=False,
    task_eager_propagates=True,
    # Retry настройки
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    worker_prefetch_multiplier=1,
    # Маршрутизация задач в очереди
    task_routes={
        'tasks.refresh_jobber_token_periodic': {'queue': 'new_leads'},
    },
    # Celery Beat schedule для периодических задач
    beat_schedule={
        'refresh-jobber-token': {
            'task': 'tasks.refresh_jobber_token_periodic',
            'schedule': 45 * 60.0,  # Каждые 45 минут (2700 секунд)
            # Токен живет 60 минут, обновляем каждые 45 минут для безопасности
        },
    },
)

# Импортируем задачи (важно: после создания celery_app)
# Это нужно для регистрации задач
from tasks import *  # noqa

