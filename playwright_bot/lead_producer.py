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
        
        # Пробуем использовать готовый профиль с авторизацией
        import os
        existing_profile = None
        for profile_dir in ["tt_profile", "playwright_bot/tt_profile", "playwright_bot/playwright_profile"]:
            full_path = os.path.join(os.getcwd(), profile_dir)
            if os.path.exists(full_path):
                existing_profile = full_path
                log.info("Found existing profile: %s", existing_profile)
                break
        
        profile_to_use = existing_profile if existing_profile else self.user_dir
        log.info("Using profile: %s", profile_to_use)
        
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=profile_to_use,
            headless=False,
            args=getattr(SETTINGS, "chromium_args", [
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage", 
                "--disable-gpu",
                "--disable-images",
                "--disable-plugins",
                "--disable-extensions",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                # Stealth mode args
                "--disable-blink-features=AutomationControlled",
                "--disable-features=VizDisplayCompositor",
                "--disable-web-security",
                "--disable-features=TranslateUI",
                "--disable-ipc-flooding-protection",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-default-apps",
                "--disable-popup-blocking",
                "--disable-hang-monitor",
                "--disable-prompt-on-repost",
                "--disable-sync",
                "--disable-translate",
                "--metrics-recording-only",
                "--no-report-upload",
                "--safebrowsing-disable-auto-update",
                "--enable-automation=false",
                "--password-store=basic",
                "--use-mock-keychain",
                "--disable-component-extensions-with-background-pages",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
                "--disable-client-side-phishing-detection",
                "--disable-crash-reporter",
                "--disable-oopr-debug-crash-dump",
                "--no-crash-upload",
                "--disable-gpu-sandbox",
                "--disable-software-rasterizer",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=TranslateUI,BlinkGenPropertyTrees",
                "--disable-ipc-flooding-protection"
            ]),
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            },
        )
        self.page = await self._ctx.new_page()
        
        # Stealth JavaScript для обхода детекции ботов
        await self.page.add_init_script("""
            // Убираем webdriver флаг
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            // Подделываем permissions API
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Подделываем plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            // Подделываем languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            
            // Убираем automation флаги
            window.chrome = {
                runtime: {},
            };
            
            // Подделываем screen properties
            Object.defineProperty(screen, 'availHeight', {
                get: () => 1040,
            });
            Object.defineProperty(screen, 'availWidth', {
                get: () => 1920,
            });
            
            // Убираем automation из window
            delete window.__playwright;
            delete window.__pw_manual;
            delete window.__webdriver_evaluate;
            delete window.__webdriver_script_func;
            delete window.__webdriver_script_fn;
            delete window.__fxdriver_evaluate;
            delete window.__driver_unwrapped;
            delete window.__webdriver_unwrapped;
            delete window.__driver_evaluate;
            delete window.__selenium_unwrapped;
            delete window.__selenium_evaluate;
            delete window.__$fxdriver_evaluate;
            delete window.__$fxdriver_unwrapped;
            delete window.__fxdriver_unwrapped;
            delete window.__webdriver_script_function;
        """)
        
        # Блокируем ненужные ресурсы для ускорения
        await self.page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "font", "media"] else route.continue_())
        
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=25000)

        log.info("LeadProducer: opened %s (url=%s)", "/pro-leads", self.page.url)

        self.bot = ThumbTackBot(self.page)
        if "login" in self.page.url.lower():
            await self.bot.login_if_needed()
            await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=25000)

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