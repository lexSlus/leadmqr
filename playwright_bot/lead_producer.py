# playwright_bot/lead_producer.py
import asyncio, logging
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
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=self.user_dir,
            headless=False,
            args=getattr(SETTINGS, "chromium_args", ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]),
            viewport=None,
        )
        self.page = await self._ctx.new_page()
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=60000)

        log.info("LeadProducer: opened %s (url=%s)", "/pro-leads", self.page.url)

        self.bot = ThumbTackBot(self.page)
        if "login" in self.page.url.lower():
            await self.bot.login_if_needed()
            await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=60000)

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