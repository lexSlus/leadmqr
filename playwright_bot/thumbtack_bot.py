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
        # Проверяем, нужен ли логин - ищем кнопки входа
        login_candidates = [
            self.page.get_by_role(LOGIN_LINK["role"], name=LOGIN_LINK["name"]),
            self.page.get_by_role(LOGIN_BTN["role"], name=LOGIN_BTN["name"])
        ]
        counts = await asyncio.gather(*(c.count() for c in login_candidates))
        if all(n == 0 for n in counts):
            return False

        if not SETTINGS.email or not SETTINGS.password:
            raise RuntimeError("No credentials provided TT_EMAIL and TT_PASSWORD")

        # Кликаем только по одной кнопке входа (не по ссылке Log in)
        for c in login_candidates:
            if await c.count():
                await c.first.click()
                break

        # Ждем загрузки страницы логина
        await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
        
        # Заполняем поля логина
        email_filled = False
        password_filled = False
        
        # Пробуем селекторы для email
        for selector in [
            'input[placeholder="Email"]',
            'input[name="email"]',
            'input[type="email"]',
            'input[id*="email"]'
        ]:
            try:
                # Сначала быстро проверим, есть ли элемент
                if await self.page.locator(selector).count() > 0:
                    await self.page.fill(selector, SETTINGS.email, timeout=2000)
                    email_filled = True
                    logger.info(f" Email заполнен через селектор: {selector}")
                    break
            except:
                continue
        
        # Пробуем селекторы для password
        for selector in [
            'input[placeholder="Password"]',
            'input[name="password"]',
            'input[type="password"]',
            'input[id*="password"]'
        ]:
            try:
                # Сначала быстро проверим, есть ли элемент
                if await self.page.locator(selector).count() > 0:
                    await self.page.fill(selector, SETTINGS.password, timeout=2000)
                    password_filled = True
                    logger.info(f" Password заполнен через селектор: {selector}")
                    break
            except:
                continue
        
        if not email_filled or not password_filled:
            logger.error(f" Не удалось заполнить поля: email={email_filled}, password={password_filled}")
            logger.error(f" URL страницы: {self.page.url}")
            logger.error(f"= Заголовок страницы: {await self.page.title()}")
            return False
        
        # Пробуем разные селекторы для кнопки входа
        login_clicked = False
        for selector in [
            'button:has-text("Log in")',
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Sign in")'
        ]:
            try:
                # Сначала быстро проверим, есть ли элемент
                if await self.page.locator(selector).count() > 0:
                    await self.page.click(selector, timeout=2000)
                    login_clicked = True
                    logger.info(f"✅ Кнопка входа нажата через селектор: {selector}")
                    break
            except:
                continue
        
        if not login_clicked:
            logger.error(" Не удалось найти кнопку входа")
            return False
        
        # Ждем загрузки страницы после логина
        try:
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except:
            # Если networkidle не сработал, ждем хотя бы domcontentloaded
            await self.page.wait_for_load_state("domcontentloaded", timeout=3000)
        return True


    async def open_leads(self):
        logger.info("[open_leads] Attempting to access pro-leads...")
        
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=10000)
        logger.info("[open_leads] Direct access, URL: %s", self.page.url)
        
        # Если все еще на login - пробуем авторизацию
        if "login" in self.page.url.lower():
            logger.info("[open_leads] Still on login, attempting authentication...")
            await self.login_if_needed()
            await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=10000)
            logger.info("[open_leads] After auth, URL: %s", self.page.url)

        # Ждём загрузку DOM
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=3000)
        except PWTimeoutError:
            pass


    async def list_new_leads(self) -> List[Dict]:
        results: List[Dict] = []
        try:
            logger.info("[list_new_leads] URL before wait: %s", self.page.url)
            await self.page.wait_for_load_state("networkidle", timeout=5000)
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
            await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        else:
            btn = self.page.get_by_role("button", name=re.compile(r"view\s*details", re.I)).nth(lead["index"])
            await btn.scroll_into_view_if_needed()
            await btn.wait_for(state="visible", timeout=5000)
            await btn.click()

        await self.page.wait_for_load_state("domcontentloaded", timeout=5000)


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
                    await btn.wait_for(state="attached", timeout=3_000)
                    # затем сделаем его видимым/прокрутим
                    try:
                        await btn.wait_for(state="visible", timeout=3_000)
                    except Exception:
                        pass
                    await btn.scroll_into_view_if_needed()
                    reply_btn = btn
                    break
                except Exception:
                    continue

            if reply_btn:
                try:
                    await reply_btn.click(timeout=3_000)
                except Exception:
                    try:
                        await reply_btn.click(timeout=2_000, force=True)
                    except Exception:
                        # не получилось кликнуть — дальше попробуем textarea
                        pass

            # после клика попробуем снова найти textarea
            box = ctx.get_by_placeholder(MSG_PLACEHOLDER)
            if await box.count() == 0:
                box = ctx.locator("textarea[placeholder]")

        # теперь работаем с textarea, если она есть
        try:
            await box.first.wait_for(state="visible", timeout=5_000)
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
            await send_btn.first.wait_for(state="visible", timeout=5_000)
            await send_btn.first.scroll_into_view_if_needed()
            await send_btn.first.click()
            try:
                await self.page.wait_for_load_state("networkidle", timeout=3_000)
            except Exception:
                pass
        except Exception:
            # не смогли нажать — мягко выходим
            return


    async def open_messages(self):
        await self.page.goto(f"{SETTINGS.base_url}/pro-inbox/", wait_until="domcontentloaded", timeout=30000)
        if "login" in self.page.url.lower():
            await self.login_if_needed()
            await self.page.goto(f"{SETTINGS.base_url}/pro-inbox/", wait_until="domcontentloaded", timeout=30000)
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
        """
        Extracts phone number from current message thread.
        Searches for existing phone numbers without clicking any buttons.
        Returns cleaned phone number (digits and + only) or None if not found.
        """
        logger.info("Searching for phone number in thread: %s", self.page.url)

        # Method 1: Look for tel: links (most reliable)
        tel_link = self.page.locator("a[href^='tel:']")
        if await tel_link.count() > 0:
            try:
                raw_href = await tel_link.first.get_attribute("href") or ""
                phone = raw_href.replace("tel:", "")
                if phone:
                    cleaned_phone = re.sub(r"[^\d+]", "", phone)
                    logger.info(f"Phone found in tel link: {phone} -> {cleaned_phone}")
                    return cleaned_phone
            except Exception as e:
                logger.error(f"Error extracting tel href: {e}")
        
        # Method 2: Look for phone text in specific element class
        phone_text_element = self.page.locator(".IUE7kXgIsvED2G8vml4Wu")
        if await phone_text_element.count() > 0:
            try:
                phone_text = await phone_text_element.first.text_content() or ""
                if phone_text:
                    cleaned_phone = re.sub(r"[^\d+]", "", phone_text)
                    logger.info(f"Phone found in text element: {phone_text} -> {cleaned_phone}")
                    return cleaned_phone
            except Exception as e:
                logger.error(f"Error extracting text content: {e}")
        
        logger.warning("Phone number not found in this thread")
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
                    "status": "skipped_already_seen",
                    "variables": {
                        "lead_id": lead_key,
                        "lead_url": f"https://www.thumbtack.com{href}",
                        "source": "thumbtack"
                    }
                })
                continue

            await row.scroll_into_view_if_needed()
            await row.click()
            try:
                await self.page.wait_for_url(re.compile(r"/pro-inbox/messages/\d+"), timeout=12000)
                logger.info("✅ URL изменился, ждем загрузки контента...")
                # Ждем загрузки контента страницы
                await self.page.wait_for_load_state("domcontentloaded")
                await self.page.wait_for_timeout(1000)  # Дополнительная пауза для загрузки
                logger.info("✅ Контент загружен, извлекаем телефон...")
            except Exception as e:
                logger.warning("⚠️ Не удалось дождаться загрузки: %s", e)

            phone = await self._show_and_extract_in_current_thread()
            if store is not None:
                store.mark_thread_seen(href, phone)

            results.append({
                "index": i,
                "href": href,
                "lead_key": lead_key,
                "phone": phone,
                "variables": {
                    "lead_id": lead_key,
                    "lead_url": f"https://www.thumbtack.com{href}",
                    "source": "thumbtack"
                }
            })
            await self.open_messages()
            threads = self._threads()
            total = max(total, await threads.count())

        return results