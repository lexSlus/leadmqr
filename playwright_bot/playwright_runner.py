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
        except Exception as e:
            logger.error("Failed to launch browser with existing profile: %s", e)
            logger.info("Falling back to new profile...")
            # Fallback к новому профилю
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
                    "--disable-renderer-backgrounding"
                ]),
                viewport={"width": 1920, "height": 1080},
            )
        
        self.page = await self._ctx.new_page()
        
        # Агрессивный Stealth JavaScript для обхода детекции ботов
        await self.page.add_init_script("""
            // Убираем webdriver флаг
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true
            });
            
            // Подделываем permissions API
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Подделываем plugins с реалистичными данными
            Object.defineProperty(navigator, 'plugins', {
                get: () => ({
                    length: 5,
                    0: { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    1: { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                    2: { name: 'Native Client', filename: 'internal-nacl-plugin' },
                    3: { name: 'Widevine Content Decryption Module', filename: 'widevinecdmadapter.dll' },
                    4: { name: 'Microsoft Edge PDF Viewer', filename: 'pdf' }
                }),
                configurable: true
            });
            
            // Подделываем languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
                configurable: true
            });
            
            // Подделываем platform
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32',
                configurable: true
            });
            
            // Подделываем hardwareConcurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8,
                configurable: true
            });
            
            // Подделываем deviceMemory
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8,
                configurable: true
            });
            
            // Убираем automation флаги
            window.chrome = {
                runtime: {
                    onConnect: undefined,
                    onMessage: undefined,
                    connect: undefined,
                    sendMessage: undefined
                },
                loadTimes: function() { return {}; },
                csi: function() { return {}; },
                app: {}
            };
            
            // Подделываем screen properties
            Object.defineProperty(screen, 'availHeight', {
                get: () => 1040,
                configurable: true
            });
            Object.defineProperty(screen, 'availWidth', {
                get: () => 1920,
                configurable: true
            });
            
            // Подделываем timezone
            Object.defineProperty(Intl.DateTimeFormat.prototype, 'resolvedOptions', {
                value: function() {
                    return { timeZone: 'America/New_York' };
                }
            });
            
            // Убираем automation из window
            const propsToDelete = [
                '__playwright', '__pw_manual', '__webdriver_evaluate', '__webdriver_script_func',
                '__webdriver_script_fn', '__fxdriver_evaluate', '__driver_unwrapped',
                '__webdriver_unwrapped', '__driver_evaluate', '__selenium_unwrapped',
                '__selenium_evaluate', '__$fxdriver_evaluate', '__$fxdriver_unwrapped',
                '__fxdriver_unwrapped', '__webdriver_script_function', '__nightmare',
                '_phantom', '__phantom', 'callPhantom', '_selenium', 'calledSelenium',
                '$cdc_asdjflasutopfhvcZLmcfl_', '$chrome_asyncScriptInfo',
                '__$webdriverAsyncExecutor', 'webdriver', '__webdriverFunc',
                '__webdriver_script_func', '__webdriver_script_fn', '__fxdriver_unwrapped',
                '__driver_unwrapped', '__webdriver_unwrapped', '__selenium_unwrapped',
                '__webdriver_evaluate', '__selenium_evaluate', '__fxdriver_evaluate'
            ];
            
            propsToDelete.forEach(prop => {
                try {
                    delete window[prop];
                } catch (e) {}
            });
            
            // Подделываем getBoundingClientRect
            const originalGetBoundingClientRect = Element.prototype.getBoundingClientRect;
            Element.prototype.getBoundingClientRect = function() {
                const rect = originalGetBoundingClientRect.call(this);
                return {
                    ...rect,
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                };
            };
            
            // Подделываем Date для стабильности
            const originalDate = Date;
            Date = function(...args) {
                if (args.length === 0) {
                    return new originalDate(originalDate.now() + Math.random() * 1000);
                }
                return new originalDate(...args);
            };
            Date.now = () => originalDate.now() + Math.random() * 1000;
            Date.prototype = originalDate.prototype;
        """)
        
        # Блокируем ненужные ресурсы для ускорения
        await self.page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "font", "media"] else route.continue_())
        
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