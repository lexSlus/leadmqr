import asyncio
import logging
import os
import uuid
import aiohttp
import json
from typing import Any, Dict, Optional
from playwright.async_api import async_playwright
from playwright_bot.config import SETTINGS
from playwright_bot.thumbtack_bot import ThumbTackBot
from playwright_bot.utils import FlowTimer
from playwright_bot.exceptions import BrokerError, AccountLockedError, NoBrowsersAvailableError


logger = logging.getLogger("playwright_bot")


class BrokerClient:
    """
    Клиент для HTTP-коммуникации с Browser Service API.
    Отвечает только за запросы acquire_lock / release_lock.
    """
    
    def __init__(self, browser_service_url: str, browser_service_token: str):
        self.browser_service_url = browser_service_url
        self.browser_service_token = browser_service_token
    
    async def acquire_lock(self, account_id: str, worker_id: str) -> Dict[str, Any]:
        """Запрашивает блокировку у Browser Service. Выбрасывает исключения при ошибках."""
        url = f"{self.browser_service_url}/acquire-lock"
        headers = {
            "Authorization": f"Bearer {self.browser_service_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "account_id": account_id,
            "worker_id": worker_id,
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                logger.info(f"[BrokerClient] Requesting lock for account {account_id} (worker: {worker_id})")
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 423:  # Locked
                        error_text = await resp.text()
                        logger.warning(f"[BrokerClient] Account {account_id} is locked: {error_text}")
                        raise AccountLockedError(error_text)
                    
                    if resp.status == 503:  # Service Unavailable
                        error_text = await resp.text()
                        logger.warning(f"[BrokerClient] No available browsers: {error_text}")
                        raise NoBrowsersAvailableError(error_text)
                    
                    # Выбрасываем исключение для других 4xx/5xx
                    resp.raise_for_status()
                    
                    data = await resp.json()
                    if data.get("status") == "success":
                        logger.info(f"[BrokerClient] Lock acquired. WS endpoint: {data.get('ws_endpoint')}, Session file: {data.get('session_file')}")
                        return data
                    else:
                        raise BrokerError(data.get("message", "Unknown error"))
        
        except (AccountLockedError, NoBrowsersAvailableError):
            # Пробрасываем эти исключения выше
            raise
        except aiohttp.ClientError as e:
            raise BrokerError(f"API Брокера недоступен: {e}")
        except Exception as e:
            logger.error(f"[BrokerClient] Unexpected exception: {e}", exc_info=True)
            raise BrokerError(f"Неожиданная ошибка: {e}")
    
    async def release_lock(self, account_id: str, worker_id: str) -> None:
        """Освобождает блокировку у Browser Service"""
        url = f"{self.browser_service_url}/release-lock"
        headers = {
            "Authorization": f"Bearer {self.browser_service_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "account_id": account_id,
            "worker_id": worker_id,
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                logger.info(f"[BrokerClient] Releasing lock for account {account_id} (worker: {worker_id})")
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        logger.info(f"[BrokerClient] Lock released successfully")
                    else:
                        error_text = await resp.text()
                        logger.error(f"[BrokerClient] Failed to release lock: {resp.status} - {error_text}")
        except Exception as e:
            logger.error(f"[BrokerClient] Exception while releasing lock: {e}", exc_info=True)
    
    async def renew_lock(self, account_id: str, worker_id: str) -> None:
        """Продлевает блокировку у Browser Service (для долгосрочных аренд)"""
        url = f"{self.browser_service_url}/renew-lock"
        headers = {
            "Authorization": f"Bearer {self.browser_service_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "account_id": account_id,
            "worker_id": worker_id,
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        logger.debug(f"[BrokerClient] Lock renewed for account {account_id}")
                    else:
                        error_text = await resp.text()
                        logger.error(f"[BrokerClient] Failed to renew lock: {resp.status} - {error_text}")
        except Exception as e:
            logger.error(f"[BrokerClient] Exception while renewing lock: {e}", exc_info=True)


class SessionManager:
    """
    Менеджер для асинхронного чтения/записи JSON-файлов сессий.
    Отвечает только за файловый I/O.
    """
    
    @staticmethod
    async def load_session(session_file: str) -> Optional[Dict[str, Any]]:
        """Асинхронно загружает session из JSON файла"""
        if not session_file:
            return None
        
        loop = asyncio.get_event_loop()
        try:
            def _load_sync():
                """Синхронная функция для загрузки session в executor"""
                # Вся блокирующая логика внутри executor
                if not os.path.exists(session_file):
                    return None
                with open(session_file, 'r') as f:
                    return json.load(f)
            
            storage_state = await loop.run_in_executor(None, _load_sync)
            
            if storage_state:
                logger.info(f"[SessionManager] Loaded session from {session_file}")
            return storage_state
        except Exception as e:
            logger.warning(f"[SessionManager] Failed to load session file {session_file}: {e}")
            return None
    
    @staticmethod
    async def save_session(session_file: str, storage_state: Dict[str, Any]) -> None:
        """Асинхронно сохраняет session в JSON файл"""
        if not session_file:
            return
        
        loop = asyncio.get_event_loop()
        try:
            def _save_sync():
                """Синхронная функция для сохранения session в executor"""
                # Вся блокирующая логика внутри executor
                session_dir = os.path.dirname(session_file)
                if session_dir and not os.path.exists(session_dir):
                    os.makedirs(session_dir, exist_ok=True)
                with open(session_file, 'w') as f:
                    json.dump(storage_state, f)
            
            await loop.run_in_executor(None, _save_sync)
            logger.info(f"[SessionManager] Saved session to {session_file}")
        except Exception as e:
            logger.error(f"[SessionManager] Failed to save session: {e}", exc_info=True)


class LeadRunner:
    """
    Чистый оркестратор бизнес-логики.
    Использует BrokerClient и SessionManager для работы с Browser Service.
    Модель: "обработчик одной задачи" с гарантированным освобождением ресурсов.
    """
    
    def __init__(self, account_id: Optional[str] = None):
        """
        Args:
            account_id: ID аккаунта для Browser Service. Если не указан, используется из конфигурации.
        """
        self.account_id = account_id or SETTINGS.account_id
        self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"  # Уникальный ID воркера
        
        # Клиенты для работы с Browser Service
        self.broker = BrokerClient(SETTINGS.browser_service_url, SETTINGS.browser_service_token)
        
        # Состояние выполнения
        self._pw = None
        self._browser = None  # Browser из WebSocket подключения
        self._ctx = None  # BrowserContext
        self.page = None
        self.bot: Optional[ThumbTackBot] = None
        self.flow = FlowTimer()
        self._lock_acquired = False  # Флаг успешного захвата блокировки

    async def process_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обработка ОДНОГО лида с гарантированным освобождением ресурсов.
        Эта функция стала единственной точкой входа для обработки лида.
        """
        lk = lead.get("lead_key")
        if not lk:
            logger.error("process_lead: no lead_key in lead: %s", lead)
            return {"ok": False, "reason": "no lead_key", "lead": lead}

        try:
            self.flow.mark(lk, "task_start")
            
            # === PHASE 1: Захват ресурсов ===
            lock_data = await self.broker.acquire_lock(self.account_id, self.worker_id)
            ws_endpoint = lock_data.get("ws_endpoint")
            session_file = lock_data.get("session_file")
            
            if not ws_endpoint:
                raise RuntimeError("No WebSocket endpoint received from Browser Service")
            
            # Помечаем, что блокировка успешно захвачена
            self._lock_acquired = True
            
            # === PHASE 2: Инициализация браузера ===
            await self._setup_browser(ws_endpoint, session_file)
            
            # === PHASE 3: Бизнес-логика обработки лида ===
            result = await self._execute_lead_processing(lead)
            
            # === PHASE 4: Сохранение состояния (ТОЛЬКО при успехе!) ===
            if result.get("ok"):
                await self._save_session(session_file)
            
            return result
            
        except (AccountLockedError, NoBrowsersAvailableError, BrokerError) as e:
            # Retriable ошибки - воркер может повторить попытку позже
            logger.warning(f"[LeadRunner] Retriable error for {self.account_id}: {e}")
            return {"ok": False, "error": str(e), "lead_key": lk, "lead": lead, "retry": True}
        
        except Exception as e:
            # Неожиданные ошибки
            logger.error(f"[LeadRunner] Critical error processing lead {lk}: {e}", exc_info=True)
            return {"ok": False, "error": str(e), "lead_key": lk, "lead": lead}
        
        finally:
            # === PHASE 5: Гарантированное освобождение ресурсов ===
            await self._cleanup_resources()

    async def _setup_browser(self, ws_endpoint: str, session_file: Optional[str]) -> None:
        """
        Фаза 2: Инициализация браузера.
        Подключается к WebSocket, загружает сессию, создает контекст.
        """
        # 1. Подключаемся к браузеру через WebSocket
        logger.info(f"[LeadRunner] Connecting to browser via WebSocket: {ws_endpoint}")
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.connect_over_cdp(ws_endpoint)
        
        # 2. Загружаем сессию, если файл существует
        storage_state = await SessionManager.load_session(session_file) if session_file else None
        
        # 3. Создаем изолированный контекст с сессией
        context_options = {
            "locale": getattr(SETTINGS, "locale", "en-US"),
        }
        if storage_state:
            context_options["storage_state"] = storage_state
        
        self._ctx = await self._browser.new_context(**context_options)
        self.page = await self._ctx.new_page()
        
        # 4. Настраиваем блокировку ресурсов для ускорения
        await self.page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "font", "media"] else route.continue_())
        
        # 5. Переходим на страницу лидов
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=25000)
        
        # 6. Инициализируем бота
        self.bot = ThumbTackBot(self.page)
        
        # 7. Проверяем, нужен ли логин
        if "login" in self.page.url.lower():
            logger.warning("[LeadRunner] Not logged in, attempting login...")
            await self.bot.login_if_needed()
            await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=25000)
        
        logger.info("[LeadRunner] Browser setup complete")

    async def _execute_lead_processing(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Фаза 3: Бизнес-логика обработки лида.
        Вся логика работы с ThumbTackBot изолирована здесь.
        """
        lk = lead.get("lead_key")
        href = lead.get("href") or ""
        logger.info("LeadRunner: processing lead %s, URL: %s", lk, self.page.url)
        
        # Шаг 1: Открываем страницу лидов
        await self.bot.open_leads()
        logger.info("LeadRunner: opened /leads, URL: %s", self.page.url)
        
        # Шаг 2: Открываем детали лида
        logger.info("LeadRunner: lead data: %s", lead)
        await self.bot.open_lead_details(lead)
        logger.info("LeadRunner: opened lead details, URL: %s", self.page.url)
        
        # Шаг 2.5: Извлекаем полное имя со страницы деталей
        full_name = await self.bot.extract_full_name_from_details()
        if full_name and full_name != lead.get('name', ''):
            logger.info("LeadRunner: extracted full name: %s (original: %s)", full_name, lead.get('name', ''))
            lead['name'] = full_name  # Обновляем имя в данных лида
        
        # Шаг 3: Отправляем шаблонное сообщение
        await self.bot.send_template_message(dry_run=False)
        logger.info("LeadRunner: sent template message (dry_run=False)")
        
        logger.info("LeadRunner: starting phone extraction for %s", lk)
        # Извлекаем телефон из первого треда
        phone = await self.bot.extract_phone()
        if phone:
            self.flow.mark(lk, "phone_found")
            logger.info("LeadRunner: phone found for %s: %s", lk, phone)
        else:
            logger.warning("LeadRunner: no phone found for %s", lk)

        result: Dict[str, Any] = {
            "ok": True,
            "lead_key": lk,
            "phone": phone,
            "variables": {
                "lead_id": lk,
                "lead_url": f"{SETTINGS.base_url}{href}",
                "name": lead.get("name") or "",
                "category": lead.get("category") or "",
                "location": lead.get("location") or "",
                "source": "thumbtack",
            },
        }
        
        # Логируем телеметрию
        durations = self.flow.durations(lk)
        total_duration = durations.get("total_s") or 0
        logger.info("LeadRunner: lead %s processed in %.3fs (durations: %s)", 
                   lk, total_duration, durations)
        
        return result

    async def _save_session(self, session_file: Optional[str]) -> None:
        """
        Сохранение сессии (вызывается только при успешном завершении обработки лида).
        НЕ вызывается в except блоках, чтобы не сохранить "битую" сессию.
        """
        if self._ctx and session_file:
            try:
                storage_state = await self._ctx.storage_state()
                await SessionManager.save_session(session_file, storage_state)
                logger.info("[LeadRunner] Session saved successfully")
            except Exception as e:
                logger.error(f"[LeadRunner] Failed to save session: {e}", exc_info=True)

    async def _cleanup_resources(self) -> None:
        """
        Освобождение ресурсов без сохранения сессии.
        Вызывается в finally блоке для гарантированного освобождения.
        """
        try:
            # 1. Закрываем контекст
            if self._ctx:
                await self._ctx.close()
            
        except Exception as e:
            logger.error(f"[LeadRunner] Error during cleanup: {e}", exc_info=True)
        finally:
            # 2. Отключаемся от браузера
            if self._browser:
                try:
                    await self._browser.disconnect()
                except Exception:
                    pass
            
            # 3. Останавливаем Playwright
            if self._pw:
                try:
                    await self._pw.stop()
                except Exception:
                    pass
            
            # 4. Освобождаем блокировку у Browser Service (если была захвачена)
            if self._lock_acquired:
                await self.broker.release_lock(self.account_id, self.worker_id)
            
            # Сбрасываем флаг
            self._lock_acquired = False
            
            # Очищаем состояние
            self._pw = None
            self._browser = None
            self._ctx = None
            self.page = None
            self.bot = None
            
            logger.info("[LeadRunner] Cleanup complete and lock released")
