"""
Jobber API integration for creating leads and clients.
Stateful клиент с автоматическим управлением токенами.
"""
import os
import logging
import requests
import time
from typing import Dict, Any, Tuple, Optional
from dotenv import load_dotenv

try:
    from gevent.lock import RLock
except ImportError:
    from threading import RLock

load_dotenv()
logger = logging.getLogger(__name__)


class JobberClient:
    """Stateful Jobber API client с автоматическим управлением токенами."""
    
    API_URL = "https://api.getjobber.com/api/graphql"
    API_VERSION = "2025-04-16"
    
    def __init__(self):
        self.client_id = os.getenv("JOBBER_CLIENT_ID")
        self.client_secret = os.getenv("JOBBER_CLIENT_SECRET")
        self.refresh_token = os.getenv("JOBBER_REFRESH_TOKEN")
        self.token_url = os.getenv("JOBBER_TOKEN_URL", "https://api.getjobber.com/api/oauth/token")
        
        self.access_token: Optional[str] = None
        self.token_expires_at: float = 0.0
        self._token_lock = RLock()
        
        # Используем Session для connection pooling и keep-alive
        # Это ускорит повторные запросы к Jobber API
        self.session = requests.Session()
        # Настройки для ускорения: keep-alive, connection pooling
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=1,
            pool_maxsize=1,
            max_retries=0
        )
        self.session.mount('https://', adapter)
        
        if not self.refresh_token:
            logger.warning("Jobber: JOBBER_REFRESH_TOKEN не найден")

    def get_valid_token(self) -> str:
        """Возвращает валидный access_token, автоматически обновляет при необходимости."""
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token

        with self._token_lock:
            if self.access_token and time.time() < self.token_expires_at:
                return self.access_token
            
            if not self.refresh_token:
                raise ValueError("JOBBER_REFRESH_TOKEN не установлен")
            
            self._refresh_token()
            
            if not self.access_token:
                raise RuntimeError("Не удалось получить access_token")
            
            return self.access_token
    
    def refresh_token_if_needed(self) -> bool:
        """
        Принудительно обновляет токен.
        Используется для периодических задач (Celery beat).
        Всегда обновляет токен без проверки валидности.
        """
        if not self.refresh_token:
            logger.warning("Jobber: refresh_token_if_needed: JOBBER_REFRESH_TOKEN не установлен")
            return False
        
        with self._token_lock:
            try:
                self._refresh_token()
                return True  # Токен обновлен
            except Exception as e:
                logger.error(f"Jobber: Ошибка при обновлении токена в периодической задаче: {e}", exc_info=True)
                return False

    def _refresh_token(self):
        """Обновляет access_token через refresh_token."""
        logger.info("Jobber: Обновление access_token...")
        refresh_start = time.time()
        
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }

        try:
            # Детальное логирование времени выполнения
            prepare_time = time.time()
            logger.debug(f"Jobber: Подготовка запроса: {(prepare_time - refresh_start)*1000:.1f}ms")
            
            # Используем Session для connection pooling
            # Уменьшаем timeout до 15 секунд (Jobber API обычно отвечает быстрее)
            request_start = time.time()
            response = self.session.post(self.token_url, data=payload, timeout=15)
            request_time = time.time() - request_start
            logger.info(f"Jobber: HTTP запрос выполнен за {request_time:.2f}с")
            
            response.raise_for_status()
            
            parse_start = time.time()
            data = response.json()
            parse_time = time.time() - parse_start
            logger.debug(f"Jobber: Парсинг JSON: {parse_time*1000:.1f}ms")

            self.access_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            self.token_expires_at = (time.time() + expires_in) - (5 * 60)
            
            refresh_time = time.time() - refresh_start
            logger.info(f"Jobber: Token обновлен за {refresh_time:.2f}с (HTTP: {request_time:.2f}с), истекает в {time.ctime(self.token_expires_at)}")
            
        except requests.exceptions.HTTPError as e:
            self.access_token = None
            self.token_expires_at = 0.0
            status = e.response.status_code if hasattr(e, 'response') and e.response else '?'
            logger.error(f"Jobber: HTTP {status} при обновлении токена: {e}")
            raise
        except requests.exceptions.RequestException as e:
            self.access_token = None
            self.token_expires_at = 0.0
            logger.error(f"Jobber: Ошибка обновления токена: {e}")
            raise

    def _make_request(self, payload: dict) -> dict:
        """Выполняет GraphQL запрос с автоматическим retry при 401."""
        access_token = self.get_valid_token()
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-JOBBER-GRAPHQL-VERSION": self.API_VERSION,
        }

        try:
            # Используем Session для connection pooling и keep-alive
            # Уменьшаем timeout до 15 секунд
            request_start = time.time()
            response = self.session.post(self.API_URL, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            request_time = time.time() - request_start
            logger.info(f"Jobber: GraphQL запрос выполнен за {request_time:.2f}с")
            return response.json()

        except requests.exceptions.HTTPError as e:
            if hasattr(e, 'response') and e.response and e.response.status_code == 401:
                logger.warning("Jobber: 401, обновляем токен и повторяем...")
                
                with self._token_lock:
                    self.access_token = None
                    self.token_expires_at = 0.0
                
                access_token = self.get_valid_token()
                headers["Authorization"] = f"Bearer {access_token}"
                
                # Используем Session для connection pooling
                response = self.session.post(self.API_URL, json=payload, headers=headers, timeout=15)
                response.raise_for_status()
                return response.json()
            else:
                logger.error(f"Jobber: HTTP Error: {e}")
                raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Jobber: Request Error: {e}")
            raise

    @staticmethod
    def split_name(full_name: str) -> Tuple[str, str]:
        """Разделяет полное имя на имя и фамилию."""
        parts = full_name.strip().split()
        if not parts:
            return "", ""
        if len(parts) > 1:
            return parts[0], " ".join(parts[1:])
        return parts[0], ""

    def create_lead(self, lead_variables: Dict[str, Any], phone: str) -> bool:
        """Создает новый лид в Jobber."""
        create_start = time.time()
        first_name, last_name = self.split_name(lead_variables.get("name", "Unknown Lead"))

        query = """
            mutation CreateLead($input: ClientCreateInput!) {
              clientCreate(input: $input) {
                client { id, isLead }
                userErrors { message, path }
              }
            }
        """
        
        variables = {
            "input": {
                "firstName": first_name,
                "lastName": last_name,
                "phones": [{"number": phone}],
                "emails": []
            }
        }
        
        payload = {"query": query, "variables": variables}

        try:
            result = self._make_request(payload)
            create_time = time.time() - create_start
            logger.info(f"Jobber: create_lead выполнен за {create_time:.2f}с")
            
            if result.get("errors"):
                logger.error(f"Jobber: GraphQL error: {result['errors']}")
                return False
            
            if result.get("data") and result["data"]["clientCreate"]["userErrors"]:
                logger.error(f"Jobber: userErrors: {result['data']['clientCreate']['userErrors']}")
                return False
            
            if result.get("data") and result["data"]["clientCreate"]["client"]:
                client_id = result["data"]["clientCreate"]["client"]["id"]
                logger.info(f"Jobber: Lead created with ID {client_id}")
                return True
            
            logger.warning("Jobber: Unexpected response format")
            return False

        except Exception as e:
            logger.error(f"Jobber: Failed to create lead: {e}", exc_info=True)
            return False


# Глобальный экземпляр для всех Celery tasks
_jobber_client = JobberClient()


def send_lead_to_jobber(lead_variables: Dict[str, Any], phone: str) -> bool:
    """Создает лид в Jobber."""
    return _jobber_client.create_lead(lead_variables, phone)


def refresh_jobber_token():
    """
    Публичная функция для периодического обновления токена Jobber.
    Используется в Celery beat задачах.
    """
    return _jobber_client.refresh_token_if_needed()
