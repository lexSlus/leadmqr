import asyncio
import logging
import os
import threading
import uuid
from typing import Any, Dict, List, Optional
from playwright.async_api import async_playwright
from playwright_bot.config import SETTINGS
from playwright_bot.state_store import StateStore
from playwright_bot.thumbtack_bot import ThumbTackBot
from playwright_bot.utils import unique_user_data_dir, FlowTimer


logger = logging.getLogger("playwright_bot")

BROWSER_WS_ENDPOINT = os.getenv("BROWSER_WS_ENDPOINT", "ws://celery_lead_producer:9222")

class LeadRunner:
    """
    Лёгкий раннер: один контекст/вкладка /pro-leads, обработка ОДНОГО лида за вызов.
    Контекст держим открытым, чтобы задачи шли быстро.
    """
    def __init__(self):
        self._started = False
        self._pw = None
        self._ctx = None
        self.page = None
        self.bot: Optional[ThumbTackBot] = None
        # Используем отдельный профиль для LeadRunner, но синхронизированный с LeadProducer
        self.user_dir = SETTINGS.user_data_dir + "_runner"
        self.flow = FlowTimer()

    async def start(self):
        if self._started:
            return
        
        try:
            self._pw = await async_playwright().start()

            # Запускаем локальный браузер (как в run_single_pass)
            logger.info("Starting local browser...")
            self._ctx = await self._pw.chromium.launch_persistent_context(
                user_data_dir=self.user_dir,
                headless=False,
                viewport=None,  # ОБЯЗАТЕЛЬНО None для --start-maximized
                args=[
                    "--start-maximized",  # Разворачиваем окно на весь экран
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-features=VizDisplayCompositor",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-extensions",
                    "--disable-plugins",
                ],
                locale=getattr(SETTINGS, "locale", "en-US"),
            )
            
            self.page = await self._ctx.new_page()
            
            await self.page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "font", "media"] else route.continue_())
            
            await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=25000)
            
            self.bot = ThumbTackBot(self.page)
            if "login" in self.page.url.lower():
                logger.warning("Not logged in, attempting manual login...")
                await self.bot.login_if_needed()
                await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=25000)
            
            self._started = True
            logger.info("LeadRunner started successfully")

        except Exception as e:
            logger.error(f"Failed to start LeadRunner: {e}", exc_info=True)
            await self.close() # Обов'язково очищуємо ресурси при помилці
            raise


    async def close(self):
        try:
            if self._ctx:
                await self._ctx.close()
        finally:
            if self._pw:
                await self._pw.stop()
        self._pw = self._ctx = self.page = self.bot = None
        self._started = False
        logger.info("LeadRunner closed")


    async def process_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обработка ОДНОГО лида:
          - открываем список /pro-leads,
          - входим в карточку, шлём шаблон,
          - (опц.) достаём телефон в Inbox,
          - возвращаем минимально нужные данные.
        """
        lk = lead.get("lead_key")
        if not lk:
            logger.error("process_lead: no lead_key in lead: %s", lead)
            return {"ok": False, "reason": "no lead_key", "lead": lead}

        try:
            self.flow.mark(lk, "task_start")
            
            if not self._started:
                await self.start()

            href = lead.get("href") or ""
            logger.info("LeadRunner: processing lead %s, URL: %s", lk, self.page.url)
            
            # Шаг 1: Открываем страницу лидов
            # await self.bot.open_leads()
            # logger.info("LeadRunner: opened /leads, URL: %s", self.page.url)
            
            # # Шаг 2: Открываем детали лида
            # logger.info("LeadRunner: lead data: %s", lead)
            # await self.bot.open_lead_details(lead)
            # logger.info("LeadRunner: opened lead details, URL: %s", self.page.url)
            
            # # Шаг 2.5: Извлекаем полное имя со страницы деталей
            # full_name = await self.bot.extract_full_name_from_details()
            # if full_name and full_name != lead.get('name', ''):
            #     logger.info("LeadRunner: extracted full name: %s (original: %s)", full_name, lead.get('name', ''))
            #     lead['name'] = full_name  # Обновляем имя в данных лида
            
            # # Шаг 3: Отправляем шаблонное сообщение
            # await self.bot.send_template_message(dry_run=False)
            # logger.info("LeadRunner: sent template message (dry_run=False)")
            
            # logger.info("LeadRunner: starting phone extraction for %s", lk)
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
            
        except Exception as e:
            logger.error("LeadRunner: error processing lead %s: %s", lk, e, exc_info=True)
            return {"ok": False, "error": str(e), "lead_key": lk, "lead": lead}