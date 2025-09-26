import logging
from typing import Dict, Any
from celery import shared_task
from django.conf import settings
from .services import TelegramService

logger = logging.getLogger('playwright_bot')


@shared_task(name="telegram_app.tasks.send_telegram_notification_task", queue="telegram")
def send_telegram_notification_task(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Асинхронно отправляет уведомление о новом лиде в Telegram.
    
    Эта задача выполняется в отдельной очереди 'telegram' и не блокирует
    основной воркер, обрабатывающий лиды.
    
    Args:
        result: Результат обработки лида от LeadRunner с ключами:
            - variables: переменные лида (name, category, location, lead_url)
            - phone: телефон клиента
            - lead_key: ID лида
    
    Returns:
        Dict с результатом выполнения:
            - success: bool - успешность отправки
            - lead_key: str - ключ лида
            - error: str - сообщение об ошибке (если есть)
    """
    try:
        # Используем сервис для отправки уведомления
        telegram_service = TelegramService()
        response = telegram_service.send_lead_notification(result)
        
        # Логируем результат
        lead_key = response.get("lead_key", "unknown")
        if response.get("success"):
            logger.info("Telegram notification sent successfully for lead %s", lead_key)
        else:
            error = response.get("error", "unknown error")
            logger.warning("Telegram notification failed for lead %s: %s", lead_key, error)
            
        return response
            
    except Exception as e:
        # Логируем критическую ошибку, но не перезапускаем задачу, чтобы не спамить
        lead_key = result.get("lead_key", "unknown")
        logger.error("Critical error in send_telegram_notification_task for lead %s: %s", 
                    lead_key, e, exc_info=True)
        return {
            "success": False,
            "lead_key": lead_key,
            "error": str(e)
        }

