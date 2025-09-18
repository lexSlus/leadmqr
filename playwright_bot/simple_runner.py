"""
Простой раннер без stealth режима для тестирования.
Использует минимальные настройки Chrome.
"""

import asyncio
import logging
from typing import Optional
from playwright.async_api import async_playwright
from playwright_bot.config import SETTINGS
from playwright_bot.thumbtack_bot import ThumbTackBot
from playwright_bot.utils import unique_user_data_dir

logger = logging.getLogger("playwright_bot")

class SimpleRunner:
    """Простой раннер без сложных stealth настроек"""
    
    def __init__(self):
        self._pw = None
        self._ctx = None
        self.page = None
        self.bot: Optional[ThumbTackBot] = None
        self._started = False
        self.user_dir = unique_user_data_dir("simple_worker")

    async def start(self):
        if self._started:
            return
            
        self._pw = await async_playwright().start()
        
        # Определяем headless режим в зависимости от окружения
        import os
        headless = not os.getenv('DISPLAY')  # headless если нет DISPLAY
        logger.info("Starting SimpleRunner in %s mode", "headless" if headless else "GUI")
        
        # Простые настройки Chrome без stealth
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=self.user_dir,
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-images",  # Ускоряем загрузку
                "--disable-plugins",
                "--disable-extensions",
            ],
            viewport={"width": 1920, "height": 1080},
        )
        
        self.page = await self._ctx.new_page()
        
        # Идем на главную страницу
        await self.page.goto(f"{SETTINGS.base_url}", wait_until="domcontentloaded", timeout=30000)
        logger.info("Simple runner started, URL: %s", self.page.url)
        
        self.bot = ThumbTackBot(self.page)
        self._started = True

    async def close(self):
        try:
            if self._ctx:
                await self._ctx.close()
        finally:
            if self._pw:
                await self._pw.stop()
        self._pw = self._ctx = self.page = self.bot = None
        self._started = False
        logger.info("Simple runner closed")

    async def test_access(self):
        """Тестирует доступ к pro-leads"""
        if not self._started:
            await self.start()
            
        logger.info("Testing access to pro-leads...")
        
        # Прямой переход
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=30000)
        logger.info("Direct access result, URL: %s", self.page.url)
        
        if "login" in self.page.url.lower():
            logger.info("Redirected to login, trying authentication...")
            try:
                await self.bot.login_if_needed()
                await asyncio.sleep(3)
                await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=30000)
                logger.info("After auth, URL: %s", self.page.url)
            except Exception as e:
                logger.error("Authentication failed: %s", e)
        else:
            logger.info("Successfully accessed pro-leads!")
            
        return self.page.url

async def test_simple_access():
    """Тестирует простой доступ без stealth"""
    runner = SimpleRunner()
    try:
        await runner.start()
        url = await runner.test_access()
        return url
    finally:
        await runner.close()

if __name__ == "__main__":
    result = asyncio.run(test_simple_access())
    print(f"Final URL: {result}")
