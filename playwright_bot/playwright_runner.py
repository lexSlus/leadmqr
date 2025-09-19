import asyncio
import logging
import os
from typing import Any, Dict, Optional
from playwright.async_api import async_playwright
from playwright_bot.config import SETTINGS
from playwright_bot.state_store import StateStore
from playwright_bot.thumbtack_bot import ThumbTackBot

from playwright_bot.utils import unique_user_data_dir

logger = logging.getLogger("playwright_bot")

BROWSER_WS_ENDPOINT = "ws://celery_lead_producer:9222"

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
        self.user_dir = unique_user_data_dir("worker")

    async def start(self):
        if self._started:
            return
        
        try:
            self._pw = await async_playwright().start()

            logger.info(f"Connecting to browser at {BROWSER_WS_ENDPOINT}...")
            self._browser = await self._pw.chromium.connect(BROWSER_WS_ENDPOINT, timeout=60000)
            logger.info("Successfully connected to the browser.")
            
            storage_state_path = "/app/pw_profiles/auth_state.json"
            if os.path.exists(storage_state_path):
                logger.info(f"Using storage state from: {storage_state_path}")
            else:
                logger.warning(f"Storage state file not found at {storage_state_path}. Will attempt to log in manually if needed.")
                storage_state_path = None

            self._ctx = await self._browser.new_context(
                storage_state=storage_state_path,
                viewport={"width": 1920, "height": 1080},
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


    async def _extract_phone_for_lead(self, lead_key: str) -> Optional[str]:
        rows = await self.bot.extract_phones_from_all_threads(store=None)
        for row in rows or []:
            if (str(row.get("lead_key") or "") == str(lead_key)) and row.get("phone"):
                phone = str(row["phone"]).strip()
                logger.info("PHONE FOUND for %s -> %s", lead_key, phone)
                return phone

        logger.info("PHONE NOT FOUND for %s (rows checked=%d)", lead_key, len(rows or []))
        return None


    async def process_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обработка ОДНОГО лида:
          - открываем список /pro-leads,
          - входим в карточку, шлём шаблон,
          - (опц.) достаём телефон в Inbox,
          - возвращаем минимально нужные данные.
        """

        if not self._started:
            await self.start()

        lk = lead.get("lead_key")
        if not lk:
            return {"ok": False, "reason": "no lead_key", "lead": lead}

        href = lead.get("href") or ""

        logger.info("Processing lead %s, URL: %s", lk, self.page.url)
        await self.bot.open_leads()
        logger.info("After open_leads, URL: %s", self.page.url)
        await self.bot.open_lead_details(lead)
        logger.info("After open_lead_details, URL: %s", self.page.url)
        await self.bot.send_template_message(dry_run=False)
        logger.info("After send_template_message")
        phone = await self._extract_phone_for_lead(lk)
        logger.info("Extracted phone for %s: %s", lk, phone)

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
            },
        }
        logger.info(f"result - {result}")
        logger.info("process_lead: phone for %s -> %s", lk, phone or "NONE")
        return result