from django.core.management.base import BaseCommand
import asyncio
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger("playwright_bot")

class Command(BaseCommand):
    help = 'Test bot detection bypass on arh.antoinevastel.com'

    def handle(self, *args, **options):
        asyncio.run(self.test_bot_detection())

    async def test_bot_detection(self):
        """Тестирует обход детекции ботов"""
        
        self.stdout.write("🤖 Testing bot detection bypass...")
        self.stdout.write("🌐 Target: https://arh.antoinevastel.com/bots/areyouheadless")
        
        async with async_playwright() as p:
            # Запускаем браузер с нашими stealth настройками
            browser = await p.chromium.launch(
                headless=False,  # Важно: headless=False для лучшего обхода
                args=[
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
                    "--disable-client-side-phishing-detection",
                    "--disable-crash-reporter",
                    "--disable-oopr-debug-crash-dump",
                    "--no-crash-upload",
                    "--disable-gpu-sandbox",
                    "--disable-software-rasterizer",
                    "--disable-features=TranslateUI,BlinkGenPropertyTrees",
                    "--disable-ipc-flooding-protection"
                ],
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
            
            page = await browser.new_page()
            
            # Агрессивный Stealth JavaScript для обхода детекции ботов
            await page.add_init_script("""
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
                    '__webdriver_unwrapped', '__selenium_unwrapped',
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
            
            try:
                # Идем на тестовый сайт
                self.stdout.write("🌐 Navigating to bot detection test...")
                await page.goto("https://arh.antoinevastel.com/bots/areyouheadless", wait_until="domcontentloaded", timeout=30000)
                
                # Ждем загрузки результата
                await page.wait_for_timeout(3000)
                
                # Получаем результат
                result_text = await page.text_content("body")
                
                self.stdout.write("\n" + "="*60)
                self.stdout.write("📊 BOT DETECTION TEST RESULTS")
                self.stdout.write("="*60)
                
                if "You are not Chrome headless" in result_text:
                    self.stdout.write("✅ SUCCESS: Bot detection bypassed!")
                    self.stdout.write("🎉 The site thinks you are a real browser")
                elif "You are Chrome headless" in result_text:
                    self.stdout.write("❌ FAILED: Bot detected!")
                    self.stdout.write("🤖 The site detected you as a headless browser")
                else:
                    self.stdout.write("⚠️  UNKNOWN: Could not determine result")
                    self.stdout.write("📄 Page content preview:")
                    self.stdout.write(result_text[:500] + "..." if len(result_text) > 500 else result_text)
                
                # Делаем скриншот для анализа
                await page.screenshot(path="bot_detection_test.png")
                self.stdout.write("📸 Screenshot saved as: bot_detection_test.png")
                
                self.stdout.write("\n💡 Tips:")
                self.stdout.write("   - If failed, try different User Agent")
                self.stdout.write("   - Check if headless=False is set")
                self.stdout.write("   - Verify JavaScript stealth injections")
                self.stdout.write("   - Consider using residential proxies")
                
            except Exception as e:
                self.stdout.write(f"❌ Error during test: {e}")
                
            finally:
                await browser.close()
                self.stdout.write("\n✅ Test completed!")
