# lead_processor.py
"""
Оркестратор бизнес-логики обработки лида.
Управляет последовательностью шагов через синхронный WebSocket клиент.
"""
import logging
import os
from typing import Dict, Any
import config
from factory_client import FactoryClient, FactoryApiError

logger = logging.getLogger(__name__)


class LeadProcessor:
    """
    Оркестратор обработки лида.
    Управляет последовательностью шагов через синхронный WebSocket клиент.
    gevent сделает все вызовы неблокирующими автоматически.
    """
    def __init__(self, account_id: str, lead_data: dict, task_id: str):
        self.account_id = account_id
        self.lead_data = lead_data
        self.req_id_base = f"lead-{self.lead_data.get('lead_key', 'unknown')}-{task_id[:8]}"
        self.client = FactoryClient(config.FACTORY_API_URL, self.req_id_base)

    def process_lead(self) -> Dict[str, Any]:
        """Выполняет весь пошаговый сценарий обработки лида (синхронно)."""
        try:
            # Подключение и старт сессии
            self.client.connect()
            self.client.start_session(self.account_id)
            
            # Выполнение шагов обработки
            self.client.execute_step("step_open_leads")
            
            self.client.execute_step(
                "step_open_lead_details",
                {"lead": self.lead_data}
            )
            
            name_result = self.client.execute_step("step_extract_full_name")
            full_name = name_result.get("full_name") if name_result else None
            
            message = self.lead_data.get("message_template")
            self.client.execute_step(
                "step_send_message",
                {"message_text": message}
            )
            
            phone_result = self.client.execute_step("step_extract_phone")
            phone = phone_result.get("phone") if phone_result else None

            # Формируем результат
            lead_key = self.lead_data.get("lead_key", "unknown")
            href = self.lead_data.get("href", "") or ""
            base_url = os.getenv("TT_BASE_URL", "https://www.thumbtack.com")
            lead_url = f"{base_url}{href}"
            client_name = full_name or self.lead_data.get("name", "") or ""
            
            variables = {
                "lead_id": lead_key,
                "lead_url": lead_url,
                "name": client_name,
                "category": self.lead_data.get("category", "") or "",
                "location": self.lead_data.get("location", "") or "",
                "source": "thumbtack",
            }
            
            logger.info(f"[{self.req_id_base}] [W1-Мозг] Сценарий ВЫПОЛНЕН. Телефон: {phone}")
            return {
                "status": "success",
                "phone": phone,
                "full_name": full_name,
                "lead_key": lead_key,
                "account_id": self.account_id,
                "variables": variables,
            }
        
        except FactoryApiError as e:
            logger.error(f"[{self.req_id_base}] [W1-Мозг] Ошибка связи с Заводом (MS): {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"[{self.req_id_base}] [W1-Мозг] Необработанная ошибка: {e}", exc_info=True)
            raise
        finally:
            # Гарантированная очистка ресурсов
            logger.info(f"[{self.req_id_base}] [W1-Мозг] Очистка ресурсов...")
            try:
                self.client.stop_session()
            except Exception as e:
                logger.warning(f"[{self.req_id_base}] [W1-Мозг] Ошибка при остановке сессии: {e}")
            finally:
                self.client.close()
