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
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=self.user_dir,
            headless=False,
            slow_mo=getattr(SETTINGS, "slow_mo", 0),
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
            viewport=None,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
        
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads",
                             wait_until="domcontentloaded", timeout=25000)
        self.bot = ThumbTackBot(self.page)
        if "login" in self.page.url.lower():
            await self.bot.login_if_needed()
            await self.page.goto(f"{SETTINGS.base_url}/pro-leads",
                                 wait_until="domcontentloaded", timeout=25000)
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