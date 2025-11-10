"""
Конфигурация для playwright_bot модуля.
Используется только как fallback в ThumbTackBot для обратной совместимости.
В новой архитектуре credentials и настройки передаются из сервисов (monitor_service, browser_service).
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """Минимальная конфигурация для обратной совместимости."""
    
    # Base URL для Thumbtack (используется в thumbtack_bot.py)
    # В новой архитектуре лучше использовать TT_BASE_URL (унифицировано с monitor_service)
    base_url: str = os.getenv("TT_BASE_URL", os.getenv("TT_BASE", "https://www.thumbtack.com"))
    
    # Message template (используется как fallback в thumbtack_bot.py)
    # В новой архитектуре передается через lead_data из monitor_service
    message_template: str = os.getenv("TT_TEMPLATE_MESSAGE", "Hi! We can help. When is a good time to talk?")
    
    # Credentials (используются в browser_service, если потребуется логин)
    # В monitor_service credentials передаются из БД, но в browser_service используются из env
    # Должны быть установлены в .env файле
    email: str = os.getenv("TT_EMAIL", "")
    password: str = os.getenv("TT_PASSWORD", "")


SETTINGS = Settings()
