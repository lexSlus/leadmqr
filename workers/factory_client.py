# factory_client.py
"""
WebSocket клиент для подключения к "Заводу" (MS).
Использует синхронную библиотеку websocket-client для работы с gevent.
"""
import json
import logging
import time
from typing import Optional, Dict, Any
import websocket

logger = logging.getLogger(__name__)


class FactoryApiError(Exception):
    """Кастомная ошибка, если "Завод" (MS) вернул 'status: error'"""
    pass


class FactoryClient:
    """
    WebSocket клиент для связи с browser_service.
    Использует синхронную библиотеку websocket-client (совместима с gevent).
    """
    def __init__(self, factory_url: str, req_id_base: str):
        # Преобразуем ws:// в формат для websocket-client
        if factory_url.startswith("ws://"):
            self.factory_url = factory_url.replace("ws://", "ws://")
        elif factory_url.startswith("wss://"):
            self.factory_url = factory_url.replace("wss://", "wss://")
        else:
            self.factory_url = factory_url
        
        self.req_id_base = req_id_base
        self.ws: Optional[websocket.WebSocket] = None
        self.session_id: Optional[str] = None
        logger.info(f"[{self.req_id_base}] [W1-Client] Инициализирован.")

    def connect(self):
        """Подключается к browser_service через WebSocket."""
        try:
            # websocket-client создает синхронное соединение
            # gevent.monkey.patch_all() сделает его неблокирующим
            self.ws = websocket.create_connection(
                self.factory_url,
                timeout=15
            )
            logger.info(f"[{self.req_id_base}] [W1-Client] Подключен к Заводу (MS).")
        except Exception as e:
            logger.error(f"[{self.req_id_base}] [W1-Client] Ошибка подключения: {e}")
            raise FactoryApiError(f"Connection error: {e}")
    
    def close(self):
        """Закрывает WebSocket соединение."""
        if self.ws:
            try:
                self.ws.close()
                logger.info(f"[{self.req_id_base}] [W1-Client] Отключен от Завода (MS).")
            except Exception as e:
                logger.warning(f"[{self.req_id_base}] [W1-Client] Ошибка при отключении: {e}")
            finally:
                self.ws = None

    def _send_and_receive(self, command: str, data: dict = None) -> Dict[str, Any]:
        """Отправляет команду и ожидает ответ (синхронно, но неблокирующе через gevent)."""
        if not self.ws:
            raise FactoryApiError("WebSocket не подключен.")
        
        req_id = f"{self.req_id_base}-{command}"
        
        # Формируем payload
        payload = {
            "command": command,
            "request_id": req_id,
            "data": data or {}
        }
        
        # Добавляем session_id для шагов (кроме session_start)
        if self.session_id and command != "session_start":
            payload["session_id"] = self.session_id
        
        logger.debug(f"[{req_id}] -> {command} (Отправка)")
        
        try:
            # Отправляем команду (gevent сделает это неблокирующим)
            self.ws.send(json.dumps(payload))
            
            # Ожидаем ответ (gevent сделает это неблокирующим)
            response_str = self.ws.recv()
            response = json.loads(response_str)
            
            if response.get("status") == "error":
                msg = response.get("error", response.get("message", "Неизвестная ошибка Завода (MS)"))
                logger.error(f"[{req_id}] <- Ошибка от Завода (MS): {msg}")
                raise FactoryApiError(msg)
            
            logger.debug(f"[{req_id}] <- {command} (Успешно)")
            return response
            
        except websocket.WebSocketException as e:
            logger.error(f"[{req_id}] WebSocket ошибка: {e}")
            raise FactoryApiError(f"WebSocket error: {e}")
        except Exception as e:
            logger.error(f"[{req_id}] Неожиданная ошибка: {e}")
            raise FactoryApiError(f"Unexpected error: {e}")
    
    def start_session(self, account_id: str) -> str:
        """Запрашивает создание новой сессии."""
        response = self._send_and_receive("session_start", {"account_id": account_id})
        self.session_id = response.get("session_id")
        if not self.session_id:
            raise FactoryApiError("Завод (MS) не вернул session_id")
        logger.info(f"[{self.req_id_base}] [W1-Client] Сессия {self.session_id} запущена.")
        return self.session_id
    
    def stop_session(self):
        """Запрашивает остановку сессии."""
        if self.session_id:
            try:
                self._send_and_receive("session_stop", {})
                logger.info(f"[{self.req_id_base}] [W1-Client] Сессия {self.session_id} остановлена.")
            except Exception as e:
                logger.warning(f"[{self.req_id_base}] [W1-Client] Ошибка при остановке сессии: {e}")
            finally:
                self.session_id = None
    
    def execute_step(self, command: str, data: dict = None) -> Any:
        """Выполняет пошаговую команду (step_...)."""
        if not self.session_id:
            raise FactoryApiError("Сессия не запущена.")
        
        if data is None:
            data = {}
        
        response = self._send_and_receive(command, data)
        return response.get("result")
