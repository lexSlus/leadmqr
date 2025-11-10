# browser_pool.py
"""
Пул браузеров для monitor_service.
Один браузер для всех мониторов аккаунтов.
"""
import asyncio
import logging
from playwright.async_api import async_playwright, Playwright, Browser

logger = logging.getLogger(__name__)


class MonitorBrowserPool:
    """
    Управляет одним "вечным" браузером для всех мониторов.
    Каждый монитор создает свой контекст (вкладку) из этого браузера.
    """
    
    def __init__(self, headless: bool = True, slow_mo: int = 100):
        self.headless = headless
        self.slow_mo = slow_mo
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self._lock = asyncio.Lock()
    
    async def start(self):
        """Запускает один браузер для всех мониторов."""
        try:
            self.playwright = await async_playwright().start()
            logger.info("Запуск браузера для мониторов...")
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo
            )
            logger.info("Браузер успешно запущен.")
        except Exception as e:
            logger.error(f"Критическая ошибка: не удалось запустить браузер: {e}", exc_info=True)
            raise
    
    async def stop(self):
        """Останавливает браузер."""
        logger.info("Остановка браузера...")
        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                logger.warning(f"Ошибка при закрытии браузера: {e}")
        
        if self.playwright:
            await self.playwright.stop()
        logger.info("Браузер остановлен.")
    
    async def get_browser(self) -> Browser:
        """
        Возвращает браузер из пула.
        Каждый монитор использует этот браузер для создания своего контекста.
        """
        if not self.browser:
            raise RuntimeError("Браузер не инициализирован.")
        return self.browser

