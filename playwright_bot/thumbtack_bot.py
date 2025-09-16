import asyncio
import hashlib
import logging

logger = logging.getLogger("playwright_bot")


from playwright.async_api import TimeoutError as PWTimeoutError
from typing import Optional, Dict, Any, List
from playwright_bot.tt_selectors import *
from playwright_bot.config import SETTINGS


RE_REPLY = re.compile(r"^\s*reply\s*$", re.I)
RE_SEND = re.compile(r"^\s*send\s*$", re.I)
MSG_PLACEHOLDER = "Answer any questions and let them know next steps."




class ThumbTackBot:
    def __init__(self, page):
        self.page = page

    async def page_is_ok(self) -> bool:
        try:
            if self.page.is_closed():
                return False
            state = await self.page.evaluate("document.readyState")
            return state in ("interactive", "complete")
        except Exception:
            return False


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


    async def list_new_leads(self) -> List[Dict]:
        results: List[Dict] = []
        try:
            await self.page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        ctx = self.page
        for fr in self.page.frames:
            if "thumbtack.com" in fr.url and fr is not self.page:
                ctx = fr
                break
        anchors = ctx.locator("a[href^='/pro-leads/']")
        view_text = re.compile(r"view\s*details", re.I)
        cards = anchors.filter(has=ctx.get_by_text(view_text))
        try:
            await cards.first.wait_for(state="visible", timeout=5000)
        except Exception:
            pass

        count = await cards.count()
        for i in range(count):
            a = cards.nth(i)
            href = await a.get_attribute("href") or ""
            title_nodes = a.locator("._3VGbA-aOhTlHiUmcFEBQs5")
            title_cnt = await title_nodes.count()
            name = await title_nodes.nth(0).inner_text() if title_cnt > 0 else ""
            category = await title_nodes.nth(1).inner_text() if title_cnt > 1 else ""
            loc_node = a.locator("svg + .flex-auto ._3iW9xguFAEzNAGlyAo5Hw7").first
            location = await loc_node.inner_text() if await loc_node.count() > 0 else ""

            item = {
                "index": i,
                "href": href,
                "lead_key": self.lead_key_from_url(href),
                "name": name.strip(),
                "category": category.strip(),
                "location": location.strip(),
                "has_view": True,
            }
            results.append(item)

        print(f"[leads] found: {len(results)}")
        for r in results:
            print(f"[lead] {r['href']} | {r.get('name', '')} | {r.get('category', '')} | {r.get('location', '')}")

        return results

    async def open_lead_details(self, lead: dict):
        """
        Открывает страницу деталей лида.
        1) Если есть href — идём напрямую (предпочтительно).
        2) Иначе кликаем по кнопке "View details" в карточке по индексу.
        """
        href = (lead or {}).get("href")
        if href:
            url = href if href.startswith("http") else f"{SETTINGS.base_url}{href}"
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        else:
            btn = self.page.get_by_role("button", name=re.compile(r"view\s*details", re.I)).nth(lead["index"])
            await btn.scroll_into_view_if_needed()
            await btn.wait_for(state="visible", timeout=5000)
            await btn.click()

        await self.page.wait_for_load_state("networkidle", timeout=20000)


    async def send_template_message(self, text: Optional[str] = None, *, dry_run: bool = False) -> None:
        text = text or SETTINGS.message_template
        # 1) Клик по Reply (форма без этого не рендерится)
        reply_btn = self.page.get_by_role("button", name=RE_REPLY)
        if await reply_btn.count() == 0:
            # подстраховка, если get_by_role не сработал
            reply_btn = self.page.locator("button", has_text=RE_REPLY)
        await reply_btn.first.wait_for(state="visible", timeout=8_000)
        await reply_btn.first.scroll_into_view_if_needed()
        await reply_btn.first.click()
        await self.page.wait_for_timeout(200)

        box = self.page.get_by_placeholder(MSG_PLACEHOLDER)
        if await box.count() == 0:
            box = self.page.locator("textarea[placeholder]")
        await box.first.wait_for(state="visible", timeout=8_000)
        await box.first.fill(text)
        if dry_run:
            print(f"[DRY RUN] message filled with: {text!r}, but not sent")
            return
        send_btn = self.page.get_by_role("button", name=RE_SEND)
        if await send_btn.count() == 0:
            send_btn = self.page.locator("button", has_text=RE_SEND)
        await send_btn.first.wait_for(state="visible", timeout=8_000)
        await send_btn.first.scroll_into_view_if_needed()
        await send_btn.first.click()

        try:
            await self.page.wait_for_load_state("networkidle", timeout=6_000)
        except Exception:
            pass


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


    def _threads(self):
        return self.page.locator("a[href^='/pro-inbox/messages']")


    async def _show_and_extract_in_current_thread(self) -> Optional[str]:

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
            if store is not None and store.should_skip_thread(href):
                results.append({
                    "index": i,
                    "href": href,
                    "lead_key": lead_key,  # 👈 добавили
                    "phone": store.phone_for_thread(href),
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
                "lead_key": lead_key,
                "phone": phone
            })
            await self.open_messages()
            threads = self._threads()
            total = max(total, await threads.count())

        return results
