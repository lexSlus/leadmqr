from playwright.sync_api import sync_playwright
from pathlib import Path
from playwright_bot.config import SETTINGS



class BrowserManager:
    def __init__(self, headless: bool | None = None):
        self._p = None
        self.browser = None
        self.ctx = None
        self.page = None
        self.headless = SETTINGS.headless if headless is None else headless

    def __enter__(self):
        self._p = sync_playwright().start()
        self.browser = self._p.chromium.launch(headless=self.headless, slow_mo=SETTINGS.slow_mo)
        storage = SETTINGS.storage_state if Path(SETTINGS.storage_state).exists() else None
        self.ctx = self.browser.new_context(storage_state=storage)
        self.page = self.ctx.new_page()
        return self

    def save_state(self):
        self.ctx.storage_state(path=SETTINGS.storage_state)

    def __exit__(self, exc_type, exc, tb):
        try:
            self.save_state()
        finally:
            if self.browser:
                self.browser.close()
            if self._p:
                self._p.stop()

