# playwright_bot/lead_producer.py
import asyncio
import logging
import uuid
from typing import Optional, Dict, Any, List
from django.conf import settings as dj_settings
from playwright.async_api import async_playwright
from celery import current_app as celery_app

from playwright_bot.config import SETTINGS
from playwright_bot.thumbtack_bot import ThumbTackBot
from playwright_bot.utils import FlowTimer
from playwright_bot.playwright_runner import BrokerClient, SessionManager
from playwright_bot.exceptions import AccountLockedError

log = logging.getLogger("playwright_bot")

# ID для LeadProducer в Browser Service
PRODUCER_ACCOUNT_ID = "producer_account"
RENEW_LOCK_INTERVAL = 600  # 10 минут


class LeadProducer:
    def __init__(self):
        self._pw = None
        self._browser = None  # Browser из WebSocket подключения
        self._ctx = None  # BrowserContext
        self.page = None
        self.bot: Optional[ThumbTackBot] = None
        self.stop_evt = asyncio.Event()
        self.flow = FlowTimer(redis_url=dj_settings.REDIS_URL)
        self.sent_leads = set()  # Кэш отправленных лидов для предотвращения дубликатов
        
        # Клиент для работы с Browser Service
        self.broker = BrokerClient(SETTINGS.browser_service_url, SETTINGS.browser_service_token)
        self.worker_id = f"producer-{uuid.uuid4().hex[:8]}"  # Уникальный ID продюсера
        self._lock_acquired = False
        self._session_file: Optional[str] = None  # Путь к файлу сессии

    async def start(self):

        # === PHASE 1: Захват ресурсов от Browser Service ===
        try:
            lock_data = await self.broker.acquire_lock(PRODUCER_ACCOUNT_ID, self.worker_id)
        except AccountLockedError:
            log.info("LeadProducer: account is already locked by another producer, exiting")
            return
        
        ws_endpoint = lock_data.get("ws_endpoint")
        self._session_file = lock_data.get("session_file")

        if not ws_endpoint:
            log.error("LeadProducer: No WebSocket endpoint received from Browser Service")
            return

        self._lock_acquired = True

        # === PHASE 2: Инициализация браузера ===
        try:
            log.info(f"LeadProducer: Connecting to browser via WebSocket: {ws_endpoint}")
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.connect_over_cdp(ws_endpoint)
        except Exception as e:
            # Если не смогли подключиться к браузеру, освобождаем лок
            log.error(f"LeadProducer: Failed to connect to browser: {e}", exc_info=True)
            await self._cleanup()
            return

        # Загружаем сессию, если файл существует
        storage_state = await SessionManager.load_session(self._session_file) if self._session_file else None

        # Создаем изолированный контекст с сессией
        context_options = {
            "locale": getattr(SETTINGS, "locale", "en-US"),
        }
        if storage_state:
            context_options["storage_state"] = storage_state

        self._ctx = await self._browser.new_context(**context_options)
        self.page = await self._ctx.new_page()

        # Блокируем ненужные ресурсы для ускорения и добавляем заголовки против кеширования
        async def handle_route(route):
            if route.request.resource_type in ["image", "font", "media"]:
                await route.abort()
            else:
                # Добавляем заголовки против кеширования для API запросов
                headers = route.request.headers
                if "api" in route.request.url or "leads" in route.request.url:
                    headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                    headers["Pragma"] = "no-cache"
                    headers["Expires"] = "0"
                await route.continue_(headers=headers)

        await self.page.route("**/*", handle_route)

        self.bot = ThumbTackBot(self.page)

        # Открываем страницу лидов и проверяем авторизацию
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=10000)
        await self._ensure_authenticated()

        # === PHASE 3: Рабочий цикл ===
        try:
            await self._loop()
        finally:
            # === PHASE 4: Очистка ===
            await self._cleanup()

    async def _ensure_authenticated(self) -> None:
        """Проверяет авторизацию и переавторизуется при необходимости"""
        if "login" in self.page.url.lower():
            log.warning("LeadProducer: redirected to login, re-authenticating...")
            await self.bot.login_if_needed()
            await self.bot.open_leads()
            
            # Сохраняем новое состояние после переавторизации
            if self._session_file:
                try:
                    storage_state = await self._ctx.storage_state()
                    await SessionManager.save_session(self._session_file, storage_state)
                except Exception as e:
                    log.warning(f"LeadProducer: Could not save auth state: {e}")

    async def _reload_page(self) -> None:
        """Перезагружает страницу с обновлением кэша"""
        await self.page.evaluate("() => { window.location.reload(true); }")
        await self.page.wait_for_load_state("domcontentloaded", timeout=10000)

    async def _process_leads(self, leads: List[Dict[str, Any]]) -> int:
        """Обрабатывает найденные лиды и возвращает количество обработанных"""
        processed_count = 0
        for lead in leads:
            lk = lead.get("lead_key")
            if not lk or lk in self.sent_leads:
                continue

            self.flow.mark(lk, "detect")
            celery_app.send_task("leads.tasks.process_lead_task", args=[lead], queue="lead_proc", retry=False)
            self.sent_leads.add(lk)
            processed_count += 1

        return processed_count

    async def _loop(self):
        """Рабочий цикл продюсера"""
        cycle_count = 0
        last_renew_time = asyncio.get_event_loop().time()
        
        while not self.stop_evt.is_set():
            try:
                cycle_count += 1

                # Продлеваем блокировку каждые 10 минут
                current_time = asyncio.get_event_loop().time()
                if current_time - last_renew_time > RENEW_LOCK_INTERVAL:
                    await self.broker.renew_lock(PRODUCER_ACCOUNT_ID, self.worker_id)
                    last_renew_time = current_time

                # Проверяем, что браузер еще открыт
                if self.page.is_closed():
                    log.error("LeadProducer: browser closed, stopping")
                    break

                # Обновляем контент
                await self._reload_page()
                await self.bot.open_leads()
                await self._ensure_authenticated()

                # Ищем и обрабатываем лиды
                leads = await self.bot.list_new_leads()
                if leads:
                    processed = await self._process_leads(leads)
                    log.info(f"LeadProducer[cycle={cycle_count}]: processed {processed}/{len(leads)} leads")

                await asyncio.sleep(5.0)

            except Exception as e:
                log.error(f"LeadProducer[cycle={cycle_count}]: error: {e}", exc_info=True)
                await asyncio.sleep(5.0)

    async def _cleanup(self):
        """Освобождение ресурсов и блокировки"""
        try:
            # 1. Закрываем контекст
            if self._ctx:
                await self._ctx.close()
        except Exception as e:
            log.error(f"LeadProducer: Error during cleanup: {e}", exc_info=True)
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
                await self.broker.release_lock(PRODUCER_ACCOUNT_ID, self.worker_id)

            self._lock_acquired = False
            log.info("LeadProducer stopped")