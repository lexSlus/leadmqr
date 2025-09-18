import asyncio
import logging
from typing import Any, Dict, Optional
from playwright.async_api import async_playwright
from playwright_bot.config import SETTINGS
from playwright_bot.state_store import StateStore
from playwright_bot.thumbtack_bot import ThumbTackBot

from playwright_bot.utils import unique_user_data_dir

logger = logging.getLogger("playwright_bot")


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
        self._pw = await async_playwright().start()
        
        # Пробуем использовать готовый профиль с авторизацией
        import os
        import shutil
        existing_profile = None
        for profile_dir in ["tt_profile", "playwright_bot/tt_profile", "playwright_bot/playwright_profile"]:
            full_path = os.path.join(os.getcwd(), profile_dir)
            if os.path.exists(full_path):
                existing_profile = full_path
                logger.info("Found existing profile: %s", existing_profile)
                
                # Удаляем lock файлы для избежания блокировки
                lock_files = ["SingletonLock", "SingletonSocket", "SingletonCookie"]
                for lock_file in lock_files:
                    lock_path = os.path.join(full_path, lock_file)
                    if os.path.exists(lock_path):
                        try:
                            os.remove(lock_path)
                            logger.info("Removed lock file: %s", lock_path)
                        except Exception as e:
                            logger.warning("Could not remove lock file %s: %s", lock_path, e)
                break
        
        profile_to_use = existing_profile if existing_profile else self.user_dir
        logger.info("Using profile: %s", profile_to_use)
        
        try:
            self._ctx = await self._pw.chromium.launch_persistent_context(
                user_data_dir=profile_to_use,
                headless=False,
                slow_mo=getattr(SETTINGS, "slow_mo", 0),
                args=[
                    "--remote-debugging-port=9222",  # Debug port
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage", 
                    "--disable-gpu",
                ],
                viewport={"width": 1920, "height": 1080},
            )
        except Exception as e:
            logger.error("Failed to launch browser with existing profile: %s", e)
            logger.info("Falling back to new profile...")
            # Fallback к новому профилю
            self._ctx = await self._pw.chromium.launch_persistent_context(
                user_data_dir=self.user_dir,
                headless=False,
                slow_mo=getattr(SETTINGS, "slow_mo", 0),
                args=[
                    "--remote-debugging-port=9222",  # Debug port
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage", 
                    "--disable-gpu",
                ],
                viewport={"width": 1920, "height": 1080},
            )
        
        self.page = await self._ctx.new_page()
        
        # Сначала проверяем авторизацию на главной странице
        await self.page.goto(f"{SETTINGS.base_url}", wait_until="domcontentloaded", timeout=25000)
        logger.info("Initial page load, URL: %s", self.page.url)
        
        self.bot = ThumbTackBot(self.page)
        
        # Проверяем авторизацию - если есть кнопка Login, значит не авторизованы
        login_elements = await self.page.locator("a:has-text('Log in'), button:has-text('Log in')").count()
        if login_elements > 0:
            logger.info("Not logged in, attempting login...")
            await self.bot.login_if_needed()
            await asyncio.sleep(2)
        
        # Теперь идем на pro-leads
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=25000)
        logger.info("After login check, URL: %s", self.page.url)
        
        # Если все еще на login, значит проблема с авторизацией
        if "login" in self.page.url.lower():
            logger.warning("Still on login page, may need manual authorization")
        else:
            logger.info("Successfully accessed pro-leads page")
            
        self._started = True
        logger.info("LeadRunner started")

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