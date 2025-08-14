import asyncio
import hashlib
import logging

logger = logging.getLogger("playwright_bot")


from playwright.async_api import TimeoutError as PWTimeoutError
from typing import Optional, Dict, Any, List
from playwright_bot.tt_selectors import *
from playwright_bot.config import SETTINGS




class ThumbTackBot:
    def __init__(self, page):
        self.page = page


    def lead_key_from_url(self, url: str) -> str:
        return hashlib.md5((url or "").encode("utf-8")).hexdigest()

    async def login_if_needed(self):

        login_btn = self.page.get_by_role("link", name=re.compile(r"^Log in$", re.I))
        if await login_btn.count():
            await login_btn.first.click()
            await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
        login_candidates = [
            self.page.get_by_role(LOGIN_LINK["role"], name=LOGIN_LINK["name"]),
            self.page.get_by_role(LOGIN_BTN["role"], name=LOGIN_BTN["name"])
        ]
        counts = await asyncio.gather(*(c.count() for c in login_candidates))
        if all(n == 0 for n in counts):
            return False

        if not SETTINGS.email or not SETTINGS.password:
            raise RuntimeError("No credentials provided TT_EMAIL and TT_PASSWORD")

        for c in login_candidates:
            if await c.count():
                await c.first.click()
                break

        await self.page.get_by_label(EMAIL_LABEL).fill(SETTINGS.email)
        await self.page.get_by_label(PASS_LABEL).fill(SETTINGS.password)
        await self.page.get_by_role(LOGIN_BTN["role"], name=LOGIN_BTN["name"]).click()
        await self.page.wait_for_load_state("networkidle", timeout=30000)
        return True


    async def open_leads(self):
        # Открываем страницу лидов напрямую
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=60000)

        # Если нас редиректнуло на логин — авторизуемся и повторяем попытку
        if "login" in self.page.url.lower():
            await self.login_if_needed()
            # await self.page.context.storage_state(path=SETTINGS.state_path)
            await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=60000)

        # На всякий случай ждём загрузку DOM
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except PWTimeoutError:
            pass

        # Если по какой-то причине мы всё ещё не на /pro-leads — кликаем по пункту меню
        if not self.page.url.rstrip("/").endswith("pro-leads"):
            leads_link = self.page.get_by_role("link", name=re.compile(r"^Leads$", re.I))
            if await leads_link.count():
                await leads_link.first.click()
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                except PWTimeoutError:
                    pass

        # --- DEBUG ---
        from pathlib import Path
        import os
        debug_dir = "/app/debug"
        os.makedirs(debug_dir, exist_ok=True)

        # Сохраняем скриншот
        await self.page.screenshot(path=f"{debug_dir}/after_open_leads.png", full_page=True)

        # Сохраняем HTML для анализа
        html_path = Path(debug_dir) / "after_open_leads.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(await self.page.content())

        # Логируем URL
        print("[DEBUG open_leads] Current URL:", self.page.url)
        # --- END DEBUG ---

    # ---------- Поиск новых лидов ----------
    async def list_new_leads(self) -> List[Dict[str, Any]]:
        """
        Возвращает список "объектов-лидов". На первом этапе можно найти карточки с кнопкой View Details.
        Позже можно расширить: вытащить id, заголовок, время, бюджет и т.д.
        """
        cards = []
        btns = self.page.get_by_role(VIEW_DETAILS["role"], name=VIEW_DETAILS["name"])
        count = await btns.count()
        for i in range(count):
            # Выше можно найти ближайший контейнер, собрать текст/атрибуты
            cards.append({"index": i, "has_view": True})
        return cards


    async def open_lead_details(self, lead: Dict[str, Any]):
        btn = self.page.get_by_role(VIEW_DETAILS["role"], name=VIEW_DETAILS["name"]).nth(lead["index"])
        await btn.scroll_into_view_if_needed()
        await btn.wait_for(state="visible", timeout=5000)
        await btn.click()
        await self.page.wait_for_load_state("networkidle", timeout=20000)


    async def send_template_message(self, text: Optional[str] = None):
        text = text or SETTINGS.message_template
        reply = self.page.get_by_role(REPLY_BTN["role"], name=REPLY_BTN["name"])
        if await reply.count():
            await reply.first.scroll_into_view_if_needed()
            await reply.first.wait_for(state="visible", timeout=5000)
            await reply.first.click()
        # поле ввода
        box = self.page.get_by_placeholder(MESSAGE_INPUT_PLACEHOLDER)
        if await box.count() == 0:
            box = self.page.locator("[contenteditable='true']")
        await box.first.wait_for(state="visible", timeout=5000)
        await box.first.fill(text)

        send_btn = self.page.get_by_role(SEND_BTN["role"], name=SEND_BTN["name"])
        await send_btn.first.wait_for(state="visible", timeout=5000)
        await send_btn.first.click()

    # 0) удобный заход в список Messages
    async def open_messages(self):
        await self.page.goto(f"{SETTINGS.base_url}/pro-inbox/", wait_until="domcontentloaded", timeout=60000)
        if "login" in self.page.url.lower():
            await self.login_if_needed()
            await self.page.goto(f"{SETTINGS.base_url}/pro-inbox/", wait_until="domcontentloaded", timeout=60000)
        try:
            await self.page.wait_for_selector("a[href^='/pro-inbox/messages']", timeout=10000)
        except PWTimeoutError:
            pass

    async def _scroll_messages_list(self, steps: int = 5):
        panel = self.page.locator("main")
        for _ in range(steps):
            try:
                await panel.evaluate("el => el.scrollTo(0, el.scrollHeight)")
                await self.page.wait_for_timeout(400)
            except Exception:
                break

    # 1) вспомогательный локатор списка тредов
    def _threads(self):
        return self.page.locator("a[href^='/pro-inbox/messages']")

    # 2) внутри открытого треда: показать номер и достать его
    async def _show_and_extract_in_current_thread(self) -> Optional[str]:
        # клик "Click to show phone number"
        logger.info("Начинаем поиск телефона в текущем треде. URL: %s", self.page.url)
        show_phone = self.page.get_by_role(SHOW_PHONE["role"], name=SHOW_PHONE["name"])
        logger.info("Кнопка number show phone: %s", show_phone.count())

        if await show_phone.count():
            logger.info(f"Найдено {show_phone.count()} ссылок с tel:")
            try:
                await show_phone.first.scroll_into_view_if_needed()
                await show_phone.first.click()
                logger.info("Клик по show phone выполнен")
            except Exception as e:
                logger.warning("Не удалось кликнуть show phone: %s", e)

        # ждать tel:
        tel_link = self.page.locator("a[href^='tel:']")
        logger.info("Ссылок tel: найдено: %s", tel_link.count())

        if await tel_link.count() == 0:
            logger.info("Ждём появления tel:...")
            try:
                await tel_link.first.wait_for(timeout=5000)
                logger.info("После ожидания ссылок tel: %s", )

            except Exception:
                pass

        if await tel_link.count():
            raw = (await tel_link.first.get_attribute("href") or "").replace("tel:", "")
            logger.info(f"Телефон найден: {raw}")

            return re.sub(r"[^\d+]", "", raw)

        # fallback текстом
        logger.info("Пробуем фолбэк по тексту (PHONE_REGEX)")
        node = self.page.get_by_text(re.compile(PHONE_REGEX))
        logger.info("Нод по PHONE_REGEX: %s", node.count())

        if await node.count():
            txt = (await node.first.text_content() or "").strip()
            logger.info("Телефон найден текстом: txt=%r -> %r", txt)

            return re.sub(r"[^\d+]", "", txt) or txt

        return None

    async def extract_phones_from_all_threads(self, store=None) -> List[Dict[str, Any]]:

        await self.open_messages()
        await self._scroll_messages_list()
        threads = self._threads()

        results: List[Dict[str, Any]] = []
        total = await threads.count()
        for i in range(total):
            row = threads.nth(i)
            href = await row.get_attribute("href") or ""
            lead_key = self.lead_key_from_url(href)

            # анти-спам по тредам
            if store is not None and store.was_thread_seen(href):
                results.append({
                    "index": i,
                    "href": href,
                    "lead_key": lead_key,  # 👈 добавили
                    "phone": None,
                    "status": "skipped_already_seen"
                })
                continue

            await row.scroll_into_view_if_needed()
            await row.click()
            try:
                await self.page.wait_for_url(re.compile(r"/pro-inbox/messages/\d+"), timeout=12000)
            except Exception:
                pass

            phone = await self._show_and_extract_in_current_thread()
            if store is not None:
                store.mark_thread_seen(href, phone)

            results.append({
                "index": i,
                "href": href,
                "lead_key": lead_key,  # 👈 добавили
                "phone": phone
            })
            await self.open_messages()
            threads = self._threads()
            total = max(total, await threads.count())

        return results
