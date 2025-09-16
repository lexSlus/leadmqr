import asyncio
import logging
from typing import Any, Dict, Optional
from playwright.async_api import async_playwright
from playwright_bot.config import SETTINGS
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
            args=getattr(SETTINGS, "chromium_args", ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]),
            viewport=None,
        )
        self.page = await self._ctx.new_page()
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads",
                             wait_until="domcontentloaded", timeout=60000)
        self.bot = ThumbTackBot(self.page)
        if "login" in self.page.url.lower():
            await self.bot.login_if_needed()
            await self.page.goto(f"{SETTINGS.base_url}/pro-leads",
                                 wait_until="domcontentloaded", timeout=60000)
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


    async def _extract_phone_for_lead(self, lead_key: str,
                                      attempts: int = 3, delay: float = 0.7) -> Optional[str]:
        """
        Открываем Inbox во второй временной вкладке и ищем телефон
        ровно для этого lead_key (несколько попыток).
        """
        inbox = await self._ctx.new_page()
        try:
            await inbox.goto(f"{SETTINGS.base_url}/pro-inbox/",
                             wait_until="domcontentloaded", timeout=60000)
            inbox_bot = ThumbTackBot(inbox)
            if "login" in inbox.url.lower():
                await inbox_bot.login_if_needed()
                await inbox.goto(f"{SETTINGS.base_url}/pro-inbox/",
                                 wait_until="domcontentloaded", timeout=60000)

            for _ in range(attempts):
                rows = await inbox_bot.extract_phones_from_all_threads()
                for row in rows or []:
                    if row.get("lead_key") == lead_key and row.get("phone"):
                        return row["phone"]
                await asyncio.sleep(delay)
            return None
        finally:
            await inbox.close()

    async def process_lead(self, lead: Dict[str, Any], *, need_phone: bool = True) -> Dict[str, Any]:
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

        await self.bot.open_leads()
        await self.bot.open_lead_details(lead)
        await self.bot.send_template_message(dry_run=False)

        result: Dict[str, Any] = {
            "ok": True,
            "lead_key": lk,
            "variables": {
                "lead_id": lk,
                "lead_url": f"{SETTINGS.base_url}{href}",
                "name": lead.get("name") or "",
                "category": lead.get("category") or "",
                "location": lead.get("location") or "",
            },
        }
        logger.info(f"result - {result}")
        if need_phone:
            result["phone"] = await self._extract_phone_for_lead(lk)

        return result