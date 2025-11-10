# telegram_notifier.py
"""
Модуль для отправки уведомлений в Telegram о новых лидах.
"""
import os
import logging
from typing import Dict, Any, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Класс для отправки уведомлений в Telegram.
    """
    def __init__(self):
        # Используем переменные из .env: TELEGRAM_TOKEN и TELEGRAM_CHAT_ID. Бля в ините это нахуярил я в шоке
        self.token = os.getenv("TELEGRAM_TOKEN")
        chat_id_str = os.getenv("TELEGRAM_CHAT_ID")
        if not chat_id_str:
            raise ValueError("TELEGRAM_CHAT_ID not found in environment variables. Please set it in .env")
        if not self.token:
            raise ValueError("TELEGRAM_TOKEN not found in environment variables. Please set it in .env")
        self.chat_id = int(chat_id_str)

    
    def send_telegram_message(self, text: str, parse_mode: str | None = "HTML") -> dict:
        """
        Базовый метод для отправки сообщения в Telegram.
        
        Args:
            text: Текст сообщения
            parse_mode: Режим парсинга (HTML, Markdown, None)
            
        Returns:
            dict: Результат отправки от Telegram API
        """
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        
        try:
            r = requests.post(url, json=payload, timeout=10)
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram API error: {data}")
            logger.info("Telegram notification sent successfully")
            return data["result"]
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}", exc_info=True)
            raise
    
    def send_lead_notification(self, variables: Dict[str, Any], phone: Optional[str]) -> dict:
        """
        Специализированный метод:
        Форматирует и отправляет уведомление о НОВОМ ЛИДЕ.
        
        Args:
            variables: Словарь с данными лида (name, category, location, lead_url)
            phone: Номер телефона клиента
            
        Returns:
            dict: Результат отправки от Telegram API
        """
        # Формируем полный URL лида, если указан только путь
        lead_url = variables.get("lead_url", "")
        if lead_url and not lead_url.startswith("http"):
            # Если это относительный путь, добавляем базовый URL
            base_url = os.getenv("TT_BASE_URL", "https://www.thumbtack.com")
            if lead_url.startswith("/"):
                lead_url = f"{base_url}{lead_url}"
            else:
                lead_url = f"{base_url}/pro-leads/{lead_url}"
        
        # Формируем сообщение
        message_text = (
            f'🚨 <b>New Lead Ready for Call!</b>\n'
            f'👤 <b>Client:</b> {variables.get("name", "Unknown")}\n'
            f'🏠 <b>Category:</b> {variables.get("category", "Unknown")}\n'
            f'📍 <b>Location:</b> {variables.get("location", "Unknown")}\n'
            f'📞 <b>PHONE:</b> <a href="tel:{phone or ""}">{phone or "Unknown"}</a>\n'
            f'🔗 <b>Link:</b> <a href="{lead_url}">Open Lead</a>'
        )
        
        # Используем базовый метод для отправки
        return self.send_telegram_message(text=message_text, parse_mode="HTML")
