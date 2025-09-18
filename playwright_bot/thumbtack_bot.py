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
        # Добавляем случайные задержки для имитации человеческого поведения
        import random
        await asyncio.sleep(random.uniform(3, 7))  # Увеличиваем задержки
        
        # Пробуем обойти капчу - меняем User Agent перед логином
        await self.page.evaluate("""
            Object.defineProperty(navigator, 'userAgent', {
                get: () => 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            });
        """)
        
        # Очищаем cookies и localStorage
        await self.page.context.clear_cookies()
        await self.page.evaluate("localStorage.clear(); sessionStorage.clear();")
        
        # Дополнительные методы обхода детекции
        await self.page.evaluate("""
            try {
                // Подделываем screen resolution
                Object.defineProperty(screen, 'width', { get: () => 1920, configurable: true });
                Object.defineProperty(screen, 'height', { get: () => 1080, configurable: true });
                Object.defineProperty(screen, 'colorDepth', { get: () => 24, configurable: true });
                
                // Подделываем timezone
                Object.defineProperty(Intl.DateTimeFormat.prototype, 'resolvedOptions', {
                    value: function() { return { timeZone: 'America/New_York' }; },
                    configurable: true
                });
                
                // Убираем все automation флаги (с проверкой)
                if (window.chrome) delete window.chrome;
                if (navigator.webdriver !== undefined) {
                    delete navigator.webdriver;
                }
                Object.defineProperty(navigator, 'webdriver', { 
                    get: () => undefined, 
                    configurable: true 
                });
            } catch (e) {
                console.log('Stealth setup error:', e);
            }
        """)
        
        await asyncio.sleep(random.uniform(2, 4))
        
        login_btn = self.page.get_by_role("link", name=re.compile(r"^Log in$", re.I))
        if await login_btn.count():
            await login_btn.first.click()
            await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
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
                
        await asyncio.sleep(random.uniform(0.5, 1.5))

        # Имитируем человеческий ввод с задержками
        email_field = self.page.get_by_label(EMAIL_LABEL)
        await email_field.click()
        await asyncio.sleep(random.uniform(0.2, 0.5))
        await email_field.fill(SETTINGS.email)
        await asyncio.sleep(random.uniform(0.3, 0.7))
        
        pass_field = self.page.get_by_label(PASS_LABEL)
        await pass_field.click()
        await asyncio.sleep(random.uniform(0.2, 0.5))
        await pass_field.fill(SETTINGS.password)
        await asyncio.sleep(random.uniform(0.5, 1.0))
        
        # Кликаем кнопку логина
        login_button = self.page.get_by_role(LOGIN_BTN["role"], name=LOGIN_BTN["name"])
        await login_button.click()
        
        # Увеличиваем таймаут для login и делаем fallback
        try:
            await self.page.wait_for_load_state("networkidle", timeout=30000)
        except PWTimeoutError:
            logger.warning("networkidle timeout, trying domcontentloaded")
            await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
        
        # Дополнительная проверка на капчу или блокировку
        if "captcha" in self.page.url.lower() or "blocked" in self.page.url.lower():
            logger.warning("Detected captcha, attempting to bypass...")
            await self.bypass_captcha()
            
        return True

    async def bypass_captcha(self):
        """Попытка обхода капчи"""
        logger.info("Attempting captcha bypass...")
        
        # Метод 1: Обновить страницу несколько раз
        for i in range(3):
            logger.info(f"Refresh attempt {i+1}/3")
            await self.page.reload(wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(5, 10))
            
            # Проверяем исчезла ли капча
            if "captcha" not in self.page.url.lower():
                logger.info("Captcha disappeared after refresh")
                return True
        
        # Метод 2: Попробовать другой URL
        logger.info("Trying alternative approach...")
        await self.page.goto(f"{SETTINGS.base_url}", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(random.uniform(3, 6))
        
        # Метод 3: Очистить все и попробовать снова
        logger.info("Clearing all data and retrying...")
        await self.page.context.clear_cookies()
        await self.page.evaluate("localStorage.clear(); sessionStorage.clear();")
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=30000)
        
        # Метод 4: Попробовать через мобильный User Agent
        logger.info("Trying mobile user agent...")
        await self.page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
        })
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=30000)
        
        # Метод 5: Попробовать через VPN имитацию
        logger.info("Trying VPN simulation...")
        await self.page.set_extra_http_headers({
            "CF-IPCountry": "US",
            "CF-Ray": "1234567890abcdef",
            "X-Forwarded-For": "192.168.1.100"
        })
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=30000)
        
        if "captcha" not in self.page.url.lower():
            logger.info("Successfully bypassed captcha")
            return True
        
        logger.error("Failed to bypass captcha")
        raise RuntimeError("Unable to bypass Thumbtack captcha")


    async def open_leads(self):
        # Альтернативный подход - пробуем разные способы доступа
        logger.info("[open_leads] Attempting to access pro-leads...")
        
        # Способ 1: Прямой переход
        try:
            await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=25000)
            logger.info("[open_leads] Direct access, URL: %s", self.page.url)
            if "login" not in self.page.url.lower():
                logger.info("[open_leads] Success! Direct access worked")
                return
        except Exception as e:
            logger.warning("[open_leads] Direct access failed: %s", e)
        
        # Способ 2: Через главную страницу
        try:
            logger.info("[open_leads] Trying via main page...")
            await self.page.goto(f"{SETTINGS.base_url}", wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(3)  # Даем время на загрузку
            
            # Ищем ссылку на leads
            leads_link = self.page.locator("a[href*='leads'], a:has-text('Leads')").first
            if await leads_link.count() > 0:
                logger.info("[open_leads] Found leads link, clicking...")
                await leads_link.click()
                await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                logger.info("[open_leads] Via link, URL: %s", self.page.url)
            else:
                # Fallback - прямой переход
                await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=25000)
                logger.info("[open_leads] Fallback direct, URL: %s", self.page.url)
        except Exception as e:
            logger.warning("[open_leads] Via main page failed: %s", e)
        
        # Если все еще на login - пробуем авторизацию
        if "login" in self.page.url.lower():
            logger.info("[open_leads] Still on login, attempting authentication...")
            try:
                await self.login_if_needed()
                await asyncio.sleep(3)
                await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=25000)
                logger.info("[open_leads] After auth, URL: %s", self.page.url)
            except Exception as e:
                logger.error("[open_leads] Authentication failed: %s", e)
                raise

        # На всякий случай ждём загрузку DOM
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
        except PWTimeoutError:
            pass

        if not self.page.url.rstrip("/").endswith("pro-leads"):
            leads_link = self.page.get_by_role("link", name=re.compile(r"^Leads$", re.I))
            if await leads_link.count():
                await leads_link.first.click()
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                except PWTimeoutError:
                    pass
        else:
            logger.info("[open_leads] Уже на странице /pro-leads, URL: %s", self.page.url)


    async def list_new_leads(self) -> List[Dict]:
        results: List[Dict] = []
        try:
            logger.info("[list_new_leads] URL before wait: %s", self.page.url)
            await self.page.wait_for_load_state("networkidle", timeout=25000)
        except Exception as e:
            logger.warning("[list_new_leads] networkidle timeout, trying domcontentloaded: %s", e)
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception as e2:
                logger.warning("[list_new_leads] domcontentloaded also failed: %s", e2)
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
            await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
        else:
            btn = self.page.get_by_role("button", name=re.compile(r"view\s*details", re.I)).nth(lead["index"])
            await btn.scroll_into_view_if_needed()
            await btn.wait_for(state="visible", timeout=5000)
            await btn.click()

        # Увеличиваем таймаут для open_lead_details
        try:
            await self.page.wait_for_load_state("networkidle", timeout=25000)
        except PWTimeoutError:
            logger.warning("networkidle timeout in open_lead_details, using domcontentloaded")
            await self.page.wait_for_load_state("domcontentloaded", timeout=15000)

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
        logger.info("extract_phones_from_all_threads: found %d threads", total)
        
        for i in range(total):
            row = threads.nth(i)
            href = await row.get_attribute("href") or ""
            lead_key = self.lead_key_from_url(href)
            logger.info("Thread %d: href=%s, lead_key=%s", i, href, lead_key)

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
            logger.info("Thread %d result: lead_key=%s, phone=%s", i, lead_key, phone)
            
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

