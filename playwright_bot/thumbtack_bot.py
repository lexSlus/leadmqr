import asyncio
import hashlib
import logging

logger = logging.getLogger("playwright_bot")


from playwright.async_api import TimeoutError as PWTimeoutError
from typing import Optional, Dict, Any, List
from playwright_bot.tt_selectors import *
from playwright_bot.config import SETTINGS


PHONE_TEXT_RE = re.compile(r"(click|show).*(phone|number)", re.I)
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
        logger.info("[open_leads] Page downloaded, URL сейчас: %s", self.page.url)
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

        if not self.page.url.rstrip("/").endswith("pro-leads"):
            leads_link = self.page.get_by_role("link", name=re.compile(r"^Leads$", re.I))
            if await leads_link.count():
                await leads_link.first.click()
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                except PWTimeoutError:
                    pass
        else:
            logger.info("[open_leads] Уже на странице /pro-leads, URL: %s", self.page.url)


    async def list_new_leads(self) -> List[Dict]:
        results: List[Dict] = []
        try:
            logger.info("[list_new_leads] URL before wait: %s", self.page.url)
            await self.page.wait_for_load_state("networkidle", timeout=8000)
        except Exception as e:
            logger.warning("[list_new_leads] wait_for_load_state failed: %s", e)
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
            logger.debug("[list_new_leads] no visible cards within timeout")

        count = await cards.count()
        logger.info("[list_new_leads] cards with 'view details': %d", count)

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
        try:
            await self.page.wait_for_url(re.compile(r"/pro-leads/\d+"), timeout=8_000)
        except Exception:
            pass

        ctx = self.page
        try:
            for fr in self.page.frames:
                if fr is not self.page and await fr.locator("textarea, button").count() > 0:
                    ctx = fr
                    break
        except Exception:
            pass

        # Если textarea уже есть — обойдёмся без Reply
        box = ctx.get_by_placeholder(MSG_PLACEHOLDER)
        if await box.count() == 0:
            box = ctx.locator("textarea[placeholder]")
        if await box.count() == 0:
            # Ищем кнопку Reply разными способами
            candidates = [
                ctx.get_by_role("button", name=RE_REPLY),
                ctx.locator("button:has-text('Reply')"),
                ctx.locator("button").filter(has_text=re.compile(r"\breply\b", re.I)),
            ]
            reply_btn = None
            for loc in candidates:
                try:
                    if await loc.count() == 0:
                        continue
                    btn = loc.first
                    # Сначала дождёмся, что элемент прикреплён
                    await btn.wait_for(state="attached", timeout=6_000)
                    # затем сделаем его видимым/прокрутим
                    try:
                        await btn.wait_for(state="visible", timeout=6_000)
                    except Exception:
                        pass
                    await btn.scroll_into_view_if_needed()
                    reply_btn = btn
                    break
                except Exception:
                    continue

            if reply_btn:
                try:
                    await reply_btn.click(timeout=6_000)
                except Exception:
                    try:
                        await reply_btn.click(timeout=4_000, force=True)
                    except Exception:
                        # не получилось кликнуть — дальше попробуем textarea
                        pass

            # после клика попробуем снова найти textarea
            box = ctx.get_by_placeholder(MSG_PLACEHOLDER)
            if await box.count() == 0:
                box = ctx.locator("textarea[placeholder]")

        # теперь работаем с textarea, если она есть
        try:
            await box.first.wait_for(state="visible", timeout=10_000)
        except Exception:
            # форма так и не появилась — выходим без падения
            return

        await box.first.fill(text)

        if dry_run:
            return
        send_btn = ctx.get_by_role("button", name=RE_SEND)
        if await send_btn.count() == 0:
            send_btn = ctx.locator("button:has-text(/^\\s*Send\\s*$/i)")
        try:
            await send_btn.first.wait_for(state="visible", timeout=10_000)
            await send_btn.first.scroll_into_view_if_needed()
            await send_btn.first.click()
            try:
                await self.page.wait_for_load_state("networkidle", timeout=6_000)
            except Exception:
                pass
        except Exception:
            # не смогли нажать — мягко выходим
            return


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

        try:
            await self.page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass

        show_btn = self.page.get_by_role("button", name=PHONE_TEXT_RE)
        if await show_btn.count() == 0:
            show_btn = self.page.locator("button:has(p:has-text(/(click|show).*(phone|number)/i))")
        if await show_btn.count() == 0:
            show_btn = self.page.locator("button").filter(has_text=re.compile(r"(phone|number)", re.I))
        btn_count = await show_btn.count()
        logger.info("Кнопок 'show phone' найдено: %d", btn_count)

        if btn_count > 0:
            b = show_btn.first
            try:
                await b.scroll_into_view_if_needed()
                # Иногда класс типа `dn s_db` мешает видимости — сначала мягкий клик...
                await b.click(timeout=8_000)
                logger.info("Клик по 'show phone' выполнен (обычный).")
            except Exception as e:
                logger.warning("Обычный клик не удался: %s — пробуем force=True", e)
                try:
                    await b.click(timeout=6_000, force=True)
                    logger.info("Клик по 'show phone' выполнен (force=True).")
                except Exception as e2:
                    logger.error("Не удалось кликнуть 'show phone' даже force=True: %s", e2)

        tel_link = self.page.locator("a[href^='tel:']")
        tel_count_before = await tel_link.count()
        logger.info("Ссылок tel: найдено до ожидания: %d", tel_count_before)

        if tel_count_before == 0:
            logger.info("Ждём появления tel:...")
            try:
                await tel_link.first.wait_for(state="attached", timeout=8_000)
            except PWTimeoutError:
                logger.warning("tel: ссылка не появилась за таймаут.")
            except Exception as e:
                logger.warning("Ожидание tel: упало: %s", e)

        tel_count_after = await tel_link.count()
        logger.info("Ссылок tel: после ожидания: %d", tel_count_after)

        if tel_count_after > 0:
            href = await tel_link.first.get_attribute("href") or ""
            raw = href.replace("tel:", "").strip()
            phone = re.sub(r"[^\d+]", "", raw)
            logger.info("Телефон найден через tel:: %s (raw=%r)", phone, raw)
            return phone or raw

        logger.info("Пробуем фолбэк по тексту (PHONE_REGEX)")
        node = self.page.get_by_text(re.compile(PHONE_REGEX))
        node_count = await node.count()
        logger.info("Нод по PHONE_REGEX: %d", node_count)

        if node_count > 0:
            txt = (await node.first.text_content() or "").strip()
            phone = re.sub(r"[^\d+]", "", txt)
            logger.info("Телефон найден текстом: %r -> %s", txt, phone or txt)
            return phone or txt

        logger.info("Телефон не найден.")
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
                    "lead_key": lead_key,
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
