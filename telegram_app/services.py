import logging
from typing import Dict, Any, Optional
from datetime import datetime
from .client import TelegramBotClient
from django.conf import settings

logger = logging.getLogger('playwright_bot')


class TelegramService:
    def __init__(self):
        # Не создаем клиент здесь, так как chat_id будет разным для каждого подписчика
        pass

    def prepare_lead_data(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Подготавливает данные лида для отправки в Telegram.
        
        Args:
            result: Результат обработки лида от LeadRunner
            
        Returns:
            Dict с подготовленными данными для отправки
        """
        variables = result.get("variables", {})
        return {
            "name": variables.get("name", "Unknown"),
            "category": variables.get("category", "Unknown"),
            "location": variables.get("location", "Unknown"),
            "phone": result.get("phone", "Unknown"),
            "lead_url": variables.get("lead_url", ""),
            "lead_key": result.get("lead_key", "Unknown")
        }

    def format_lead_message(self, lead_data: Dict[str, Any]) -> str:
        """
        Форматирует сообщение о лиде для отправки в Telegram
        
        Args:
            lead_data: Данные лида
            
        Returns:
            Отформатированное сообщение
        """
        name = lead_data.get('name', 'Unknown')
        category = lead_data.get('category', 'Unknown')
        location = lead_data.get('location', 'Unknown')
        phone = lead_data.get('phone', 'Unknown')
        lead_url = lead_data.get('lead_url', '')
        lead_key = lead_data.get('lead_key', 'Unknown')
        
        # Форматируем сообщение с эмодзи и HTML разметкой
        message = f"""
🚨 <b>New Lead Ready for Call!</b>

👤 <b>Client:</b> {name}
🏠 <b>Category:</b> {category}
📍 <b>Location:</b> {location}
📞 <b>PHONE:</b> <code>{phone}</code>
🔗 <b>Link:</b> <a href="{lead_url}">Open Lead</a>

⏰ <b>Time:</b> {self._get_current_time()}
🆔 <b>Lead ID:</b> {lead_key}
"""
        
        return message.strip()

    def _get_current_time(self) -> str:
        """Возвращает текущее время в формате для отображения (Miami timezone)"""
        import pytz
        miami_tz = pytz.timezone('America/New_York')  # Miami uses Eastern Time
        miami_time = datetime.now(miami_tz)
        return miami_time.strftime("%Y-%m-%d %H:%M:%S EST")

    def is_enabled(self) -> bool:
        """Проверяет, включены ли Telegram уведомления."""
        return settings.TELEGRAM_ENABLED

    def is_configured(self) -> bool:
        """Проверяет, настроены ли необходимые параметры."""
        return bool(settings.TELEGRAM_BOT_TOKEN and self.has_subscribers())
    
    def has_subscribers(self) -> bool:
        """Проверяет, есть ли подписчики в базе данных."""
        try:
            from .models import TelegramSubscriber
            return TelegramSubscriber.objects.exists()
        except Exception:
            return False

    def send_lead_notification(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Отправляет уведомление о новом лиде в Telegram.
        
        Args:
            result: Результат обработки лида от LeadRunner
            
        Returns:
            Dict с результатом выполнения:
                - success: bool - успешность отправки
                - lead_key: str - ключ лида
                - error: str - сообщение об ошибке (если есть)
        """
        # Подготавливаем данные
        lead_data = self.prepare_lead_data(result)
        lead_key = lead_data.get("lead_key", "unknown")
        
        # Проверяем, включены ли уведомления
        if not self.is_enabled():
            return {
                "success": False,
                "lead_key": lead_key,
                "error": "Telegram notifications disabled"
            }
        
        # Проверяем конфигурацию
        if not self.is_configured():
            return {
                "success": False,
                "lead_key": lead_key,
                "error": "Telegram not configured"
            }
        
        # Форматируем сообщение и отправляем уведомление всем подписчикам
        try:
            from .models import TelegramSubscriber
            
            message = self.format_lead_message(lead_data)
            subscribers = TelegramSubscriber.objects.all()
            
            if not subscribers.exists():
                return {
                    "success": False,
                    "lead_key": lead_key,
                    "error": "No subscribers found"
                }
            
            # Отправляем уведомление всем подписчикам
            success_count = 0
            total_count = subscribers.count()
            
            for subscriber in subscribers:
                try:

                    client = TelegramBotClient()
                    client.chat_id = str(subscriber.chat_id)
                    
                    success = client.send_lead_notification(message)
                    if success:
                        success_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to send notification to subscriber {subscriber.chat_id}: {e}")
            
            if success_count > 0:
                return {
                    "success": True,
                    "lead_key": lead_key,
                    "error": None,
                    "sent_to": f"{success_count}/{total_count} subscribers"
                }
            else:
                return {
                    "success": False,
                    "lead_key": lead_key,
                    "error": "Failed to send to any subscribers"
                }
                
        except Exception as e:
            return {
                "success": False,
                "lead_key": lead_key,
                "error": str(e)
            }
