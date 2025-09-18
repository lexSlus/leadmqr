# playwright_bot/lead_producer.py
import asyncio, logging
import os
import shutil
from typing import Optional, Dict, Any, List
import redis.asyncio as aioredis
from django.conf import settings as dj_settings
from playwright.async_api import async_playwright
from celery import current_app as celery_app

from playwright_bot.config import SETTINGS
from playwright_bot.thumbtack_bot import ThumbTackBot
from playwright_bot.utils import unique_user_data_dir, FlowTimer


log = logging.getLogger("playwright_bot")

HEARTBEAT_KEY = "tt:runner:hb"
HEARTBEAT_TTL = 15
LEASE_KEY     = "tt:runner:lease"
LEASE_TTL     = 30
ENQ_TTL       = 90

class LeadProducer:
    def __init__(self):
        self._pw = None
        self._ctx = None
        self.page = None
        self.bot: Optional[ThumbTackBot] = None
        self.stop_evt = asyncio.Event()
        self.redis: Optional[aioredis.Redis] = None
        self.user_dir = unique_user_data_dir("producer")
        self.flow = FlowTimer(redis_url=dj_settings.REDIS_URL)

    async def _acquire(self) -> bool:
        return bool(await self.redis.set(LEASE_KEY, "1", ex=LEASE_TTL, nx=True))

    async def _renew(self):  await self.redis.expire(LEASE_KEY, LEASE_TTL)
    async def _hb(self):     await self.redis.set(HEARTBEAT_KEY, "1", ex=HEARTBEAT_TTL)

    async def start(self):
        self.redis = await aioredis.from_url(dj_settings.REDIS_URL, decode_responses=True)
        if not await self._acquire():
            log.info("LeadProducer: lease exists, skip")
            return

        self._pw = await async_playwright().start()
        
        # Пробуем использовать готовый профиль с авторизацией
        existing_profile = None
        for profile_dir in ["tt_profile", "playwright_bot/tt_profile", "playwright_bot/playwright_profile"]:
            full_path = os.path.join(os.getcwd(), profile_dir)
            if os.path.exists(full_path):
                existing_profile = full_path
                log.info("Found existing profile: %s", existing_profile)
                
                # Удаляем lock файлы для избежания блокировки
                lock_files = ["SingletonLock", "SingletonSocket", "SingletonCookie", "SingletonLock.tmp", "LockFile"]
                for lock_file in lock_files:
                    lock_path = os.path.join(full_path, lock_file)
                    if os.path.exists(lock_path):
                        try:
                            os.remove(lock_path)
                            log.info("Removed lock file: %s", lock_path)
                        except Exception as e:
                            log.warning("Could not remove lock file %s: %s", lock_path, e)
                
                # Удаляем весь профиль если он заблокирован
                try:
                    import subprocess
                    result = subprocess.run(['lsof', full_path], capture_output=True, text=True)
                    if result.returncode == 0 and result.stdout:
                        log.warning("Profile in use, removing entire profile directory")
                        shutil.rmtree(full_path)
                        existing_profile = None
                except Exception as e:
                    log.warning("Could not check profile usage: %s", e)
                break
        
        profile_to_use = existing_profile if existing_profile else self.user_dir
        log.info("Using profile: %s", profile_to_use)
        
        try:
            self._ctx = await self._pw.chromium.launch_persistent_context(
                user_data_dir=profile_to_use,
                headless=False,
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
            log.error("Failed to launch browser with existing profile: %s", e)
            log.info("Falling back to new profile...")
            # Fallback к новому профилю
            self._ctx = await self._pw.chromium.launch_persistent_context(
                user_data_dir=self.user_dir,
                headless=False,
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
        log.info("Initial page load, URL: %s", self.page.url)
        
        self.bot = ThumbTackBot(self.page)
        
        # Проверяем авторизацию - если есть кнопка Login, значит не авторизованы
        login_elements = await self.page.locator("a:has-text('Log in'), button:has-text('Log in')").count()
        if login_elements > 0:
            log.info("Not logged in, attempting login...")
            await self.bot.login_if_needed()
            await asyncio.sleep(2)
        
        # Теперь идем на pro-leads
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=25000)
        log.info("After login check, URL: %s", self.page.url)
        
        # Если все еще на login, значит проблема с авторизацией
        if "login" in self.page.url.lower():
            log.warning("Still on login page, may need manual authorization")
        else:
            log.info("Successfully accessed pro-leads page")

        try:
            await self._loop()
        finally:
            try: await self._ctx.close()
            except: pass
            try: await self._pw.stop()
            except: pass
            try: await self.redis.delete(LEASE_KEY)
            except: pass
            log.info("LeadProducer stopped")

    async def _loop(self):
        while not self.stop_evt.is_set():
            await self._renew()
            await self._hb()

            await self.bot.open_leads()
            log.info("LeadProducer: opened %s (url=%s)", "/leads", self.page.url)
            leads: List[Dict[str, Any]] = await self.bot.list_new_leads()
            for lead in leads:
                lk = lead.get("lead_key")
                if not lk:
                    log.warning("LeadProducer[%d]: skip lead without lead_key: %s", lead)
                    continue

                self.flow.mark(lk, "detect")

                if not await self.redis.set(f"lead:enq:{lk}", "1", ex=ENQ_TTL, nx=True):
                    continue
                celery_app.send_task(
                    "leads.tasks.process_lead_task",
                    args=[lead],
                    queue="lead_proc",
                    retry=False,
                )
                log.info("LeadProducer: enqueued %s", lk)

            await asyncio.sleep(1.0 if leads else 1.8)