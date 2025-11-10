# config.py
"""
Конфигурация для сервиса мониторинга (Monitor Service).
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class MonitorConfig:
    """Конфигурация сервиса мониторинга."""
    
    # RabbitMQ для отправки задач
    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672//")
    celery_broker_url: str = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
    
    # Очередь для отправки задач
    queue_name: str = os.getenv("CELERY_QUEUE_NAME", "new_leads")
    
    # Имя задачи Celery (должно совпадать с tasks.py в workers)
    task_name: str = os.getenv("MONITOR_TASK_NAME", "tasks.process_new_lead")
    
    # Thumbtack настройки
    base_url: str = os.getenv("TT_BASE_URL", "https://www.thumbtack.com")
    poll_interval_sec: float = float(os.getenv("TT_POLL_INTERVAL_SEC", "3.0"))  # как часто проверять лиды
    restart_interval_sec: int = int(os.getenv("TT_RESTART_INTERVAL_SEC", "10800"))  # полный рестарт каждые 3 часа
    
    # Playwright настройки
    headless: bool = os.getenv("TT_HEADLESS", "True").lower() == "true"
    slow_mo: int = int(os.getenv("TT_SLOW_MO", "100"))
    
    # БД настройки (для чтения аккаунтов)
    # Формат: postgresql+asyncpg://user:password@host:port/database
    # Если не указан или недоступен, используется fallback на переменные окружения
    db_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://thumbtack:thumbtack@postgres:5432/thumbtack")
    
    # Папка для хранения сессий
    sessions_dir: str = os.getenv("MONITOR_SESSIONS_DIR", "monitor_sessions")
    
    # Логирование
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


CONFIG = MonitorConfig()

