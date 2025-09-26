from playwright.sync_api import sync_playwright
from pathlib import Path
from playwright_bot.config import SETTINGS

class BrowserManager:
    def __init__(self, headless: bool | None = None):
        self._p = None
        self.browser = None
        self.ctx = None
        self.page = None
        # Цей параметр тепер не використовується при підключенні, але нехай залишається
        self.headless = SETTINGS.headless if headless is None else headless

    def __enter__(self):
        self._p = sync_playwright().start()
        # Запускаем собственный браузер
        self.browser = self._p.chromium.launch(headless=self.headless, slow_mo=SETTINGS.slow_mo)
        
        storage = SETTINGS.storage_state if Path(SETTINGS.storage_state).exists() else None
        self.ctx = self.browser.new_context(storage_state=storage)
        self.page = self.ctx.new_page()
        return self

    def save_state(self):
        # Переконуємось, що контекст ще існує перед збереженням
        if self.ctx:
            self.ctx.storage_state(path=SETTINGS.storage_state)

    def __exit__(self, exc_type, exc, tb):
        try:
            self.save_state()
        finally:
            # Закриваємо контекст і сторінку
            if self.page:
                self.page.close()
            if self.ctx:
                self.ctx.close()
            # Закриваємо браузер
            if self.browser:
                self.browser.close()
            # Зупиняємо клієнт Playwright
            if self._p:
                self._p.stop()