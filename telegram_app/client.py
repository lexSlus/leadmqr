import requests
import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger('playwright_bot')


class TelegramBotClient:
    def __init__(self, chat_id: str = None):
        from django.conf import settings
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id  # Теперь chat_id передается как параметр
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    def do_request(self, endpoint: str, method: str = 'POST', payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Выполняет HTTP запрос к Telegram API
        
        Args:
            endpoint: API endpoint (например, 'sendMessage')
            method: HTTP метод
            payload: Данные для отправки
            
        Returns:
            Ответ от API в формате JSON
        """
        url = f"{self.base_url}/{endpoint}"
        
        try:
            if method == 'POST':
                response = requests.post(url, json=payload, timeout=10)
            elif method == 'GET':
                response = requests.get(url, params=payload, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            
            if response.text.strip():
                return response.json()
            else:
                logger.info("Received empty response from Telegram API, treating as success")
                return {"ok": True, "message": "Empty response"}
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Telegram API request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to parse Telegram API response: {e}")
            logger.error(f"Response text: {response.text}")
            raise
    
    def send_lead_notification(self, message: str) -> bool:
        """
        Отправляет уведомление о новом лиде менеджеру
        
        Args:
            message: Готовое отформатированное сообщение для отправки
        
        Returns:
            bool: True если сообщение отправлено успешно
        """
        try:
            # Отправляем через API
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            
            response = self.do_request("sendMessage", method="POST", payload=payload)
            
            if response.get("ok"):
                logger.info("Telegram notification sent successfully")
                return True
            else:
                logger.error(f"Telegram API returned error: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False
    
    def send_test_message(self) -> bool:
        """
        Отправляет тестовое сообщение для проверки работы бота
        
        Returns:
            bool: True если тест прошел успешно
        """
        try:
            message = "🤖 <b>Тест подключения</b>\n\nTelegram бот работает корректно!"
            
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            
            response = self.do_request("sendMessage", method="POST", payload=payload)
            
            if response.get("ok"):
                logger.info("Test Telegram message sent successfully")
                return True
            else:
                logger.error(f"Telegram test message failed: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send test Telegram message: {e}")
            return False
    
    
    def _get_current_time(self) -> str:
        """Возвращает текущее время в формате для отображения"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
