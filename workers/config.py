# config.py
"""
Конфигурация для "Рабочих" (Celery Workers).
"""
import os
from dataclasses import dataclass

@dataclass
class WorkerConfig:
    """Конфигурация воркера."""
    
    # RabbitMQ
    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672//")
    
    # Celery
    celery_broker_url: str = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
    celery_result_backend: str = os.getenv("CELERY_RESULT_BACKEND", "rpc://")
    
    # Factory (MS) WebSocket API
    factory_ws_url: str = os.getenv("FACTORY_WS_URL", "ws://localhost:8080/api/ws")
    # Алиас для совместимости с factory_client.py
    FACTORY_API_URL: str = os.getenv("FACTORY_WS_URL", "ws://localhost:8080/api/ws")
    
    # Celery Worker Pool
    worker_pool: str = os.getenv("CELERY_WORKER_POOL", "gevent")  # gevent или eventlet
    worker_concurrency: int = int(os.getenv("CELERY_WORKER_CONCURRENCY", "50"))
    
    # Очереди
    queue_name: str = os.getenv("CELERY_QUEUE_NAME", "new_leads")
    
    # Retry настройки
    max_retries: int = int(os.getenv("CELERY_MAX_RETRIES", "3"))
    retry_countdown: int = int(os.getenv("CELERY_RETRY_COUNTDOWN", "60"))  # секунды


CONFIG = WorkerConfig()

# Для обратной совместимости с factory_client.py
FACTORY_API_URL = CONFIG.FACTORY_API_URL

