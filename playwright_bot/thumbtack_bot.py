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
        """
        ✔️ ИЗМЕНЕНО: Максимально упрощенный метод. Только навигация и логин.
        Никаких ожиданий контента.
        """
        logger.info("ThumbTackBot: opening /pro-leads page...")
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=15000)
        
        if "login" in self.page.url.lower():
            logger.warning("ThumbTackBot: login page detected, attempting authentication...")
            await self.login_if_needed()
            # После логина снова переходим на нужную страницу для чистоты эксперимента
            await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=15000)

        logger.info("ThumbTackBot: navigation to /pro-leads complete. Current URL: %s", self.page.url)


    async def list_new_leads(self) -> List[Dict]:
        """
        ✔️ ИЗМЕНЕНО: Надежно находит новые лиды, используя явное ожидание
        появления карточек вместо ожидания состояния сети.
        """
        results: List[Dict] = []
        ctx = self.page # По умолчанию работаем с основной страницей
        
        # Попытка найти активный фрейм, если он есть
        for fr in self.page.frames:
            if "thumbtack.com" in fr.url and fr is not self.page:
                ctx = fr
                break

        # Определяем локатор для карточек с лидами
        anchors = ctx.locator("a[href^='/pro-leads/']")
        view_text = re.compile(r"view\s*details", re.I)
        cards = anchors.filter(has=ctx.get_by_text(view_text))

        try:
            # ГЛАВНОЕ ИЗМЕНЕНИЕ: Терпеливо ждем появления первой карточки.
            # Даем ей до 20 секунд, чтобы React успел все загрузить и отрисовать.
            await cards.first.wait_for(state="visible", timeout=20000)
            logger.info("[list_new_leads] Lead cards are visible. Proceeding with extraction.")
        except PWTimeoutError:
            # Если за 20 секунд ничего не появилось, значит, новых лидов действительно нет.
            logger.info("[list_new_leads] No lead cards found within the timeout. Assuming no new leads.")
            print("[leads] found: 0")
            return results

        # Если мы дошли досюда, карточки точно есть на странице.
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

            if href.startswith("/pro-leads/"):
                lead_id = href.replace("/pro-leads/", "")
            else:
                lead_id = hashlib.md5((href or "").encode("utf-8")).hexdigest()[:12]
            
            item = {
                "index": i,
                "href": href,
                "lead_id": lead_id,
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
            await self.page.goto(url, wait_until="domcontentloaded", timeout=10000)
        else:
            btn = self.page.get_by_role("button", name=re.compile(r"view\s*details", re.I)).nth(lead["index"])
            await btn.scroll_into_view_if_needed()
            await btn.wait_for(state="visible", timeout=5000)
            await btn.click()

        await self.page.wait_for_load_state("domcontentloaded", timeout=3000)
        


    async def extract_full_name_from_details(self) -> Optional[str]:
        """
        Извлекает полное имя клиента со страницы деталей лида.
        Пробует несколько селекторов для поиска имени.
        """
        try:
            # Селекторы для поиска имени на странице деталей
            name_selectors = [
                "h1",  # Основной заголовок
                "[data-testid*='name']",  # По data-testid
                "._3VGbA-aOhTlHiUmcFEBQs5",  # Тот же селектор, что используется в списке
                ".text-xl",  # Большой текст
                ".font-semibold",  # Жирный текст
                "h2",  # Заголовок второго уровня
                ".lead-name",  # Специфичный класс для имени лида
            ]
            
            for selector in name_selectors:
                try:
                    name_element = self.page.locator(selector).first
                    if await name_element.count() > 0:
                        name_text = await name_element.inner_text()
                        if name_text and len(name_text.strip()) > 0:
                            # Проверяем, что это похоже на имя (содержит буквы)
                            if re.search(r'[a-zA-Z]', name_text):
                                return name_text.strip()
                except Exception:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting full name from details: {e}")
            return None


    async def send_template_message(self, text: Optional[str] = None, *, dry_run: bool = False) -> None:
        text = text or SETTINGS.message_template
        logger.info(f"ThumbTackBot: send_template_message started, dry_run={dry_run}")
        logger.info(f"ThumbTackBot: current URL: {self.page.url}")
        
        try:
            await self.page.wait_for_url(re.compile(r"/pro-leads/\d+"), timeout=8_000)
            logger.info("ThumbTackBot: successfully waited for pro-leads URL")
        except Exception as e:
            logger.warning(f"ThumbTackBot: failed to wait for pro-leads URL: {e}")
        
        
        # Ждем загрузки страницы
        await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
        logger.info("ThumbTackBot: page loaded, starting message sending process")
        
        # Ожидание загрузки React с retry логикой (как в open_messages)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Ждем, пока корневой div (#app-page-root) наполнится контентом
                await self.page.wait_for_function(
                    "document.querySelector('#app-page-root')?.childElementCount > 0",
                    timeout=30000
                )
                logger.info(f"ThumbTackBot: React loaded successfully (attempt {attempt + 1})")
                break  # Успешно загрузилось, выходим из цикла

            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"ThumbTackBot: React load attempt {attempt + 1} failed: {e}, retrying...")
                    # Делаем refresh и ждем
                    await self.page.reload(wait_until="domcontentloaded", timeout=30000)
                    await self.page.wait_for_timeout(2000)
                else:
                    logger.error(f"ThumbTackBot: React failed to load after {max_retries} attempts: {e}")
                    # Сохраняем диагностику
                    await self._run_diagnostics("react_load_failure_lead_page")
        
        # Дополнительное ожидание для стабильности
        await self.page.wait_for_timeout(2000)
        logger.info("ThumbTackBot: additional 2s wait completed")
        
        # Проверяем и закрываем модальные окна
        try:
            modal_close_buttons = await self.page.locator("[data-test*='modal'], [role='dialog'] button, .modal button").count()
            if modal_close_buttons > 0:
                # Пытаемся закрыть модальные окна
                for i in range(modal_close_buttons):
                    try:
                        close_btn = self.page.locator("[data-test*='modal'], [role='dialog'] button, .modal button").nth(i)
                        if await close_btn.is_visible():
                            await close_btn.click()
                            await self.page.wait_for_timeout(500)
                    except Exception:
                        pass
        except Exception:
            pass
        
        # Ищем стрелочку для закрытия правой колонки и показа кнопки Reply
        # Проверяем, есть ли стрелочка, и кликаем только если она найдена
        try:
            arrow_selectors = [
                "div.absolute.bg-white.pt2.pl2.wPfqh3o7sI2wx1pi8F3Jv[role='button']",
                "svg[height='28'][width='28'] path[d*='M10.764 21.646L19 14l-8.275-7.689a1 1 0 00-1.482 1.342L16 14l-6.699 6.285c-.187.2-.301.435-.301.715a1 1 0 001 1c.306 0 .537-.151.764-.354z']",
                "svg path[d*='M10.764 21.646L19 14l-8.275-7.689']",
                "div.wPfqh3o7sI2wx1pi8F3Jv[role='button']",
            ]
            
            arrow_found = False
            for i, selector in enumerate(arrow_selectors):
                arrow = self.page.locator(selector)
                count = await arrow.count()
                if count > 0:
                    arrow_found = True
                    await arrow.first.scroll_into_view_if_needed()
                    await arrow.first.click()
                    await self.page.wait_for_timeout(500)  # Сократили время ожидания после клика
                    break
            
            if not arrow_found:
                # Стрелочка не найдена, возможно кнопка Reply уже видна
                pass
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
        logger.info(f"ThumbTackBot: looking for textarea with placeholder: '{MSG_PLACEHOLDER}'")
        box = ctx.get_by_placeholder(MSG_PLACEHOLDER)
        box_count = await box.count()
        logger.info(f"ThumbTackBot: found {box_count} textareas with specific placeholder")
        
        if box_count == 0:
            box = ctx.locator("textarea[placeholder]")
            box_count = await box.count()
            logger.info(f"ThumbTackBot: found {box_count} textareas with any placeholder")
        
        if box_count == 0:
            logger.info("ThumbTackBot: no textarea found, looking for Reply button")
            
            # Дополнительное ожидание для появления кнопок (как в open_messages)
            try:
                # Ждем появления хотя бы одной кнопки на странице
                await ctx.locator("button").first.wait_for(timeout=10000)
            except Exception:
                pass
            
            # Ищем кнопку Reply разными способами
            candidates = [
                ctx.get_by_role("button", name=RE_REPLY),
                ctx.locator("button:has-text('Reply')"),
                ctx.locator("button").filter(has_text=re.compile(r"\breply\b", re.I)),
                # Новые селекторы по CSS классам
                ctx.locator("button._1iRY-9hq7N_ErfzJ6CdfXn:has(span:has-text('Reply'))"),
                ctx.locator("button:has(span._2CV_W3BKnouk-HUw1DACuL:has-text('Reply'))"),
            ]
            reply_btn = None
            for i, loc in enumerate(candidates):
                try:
                    count = await loc.count()
                    if count == 0:
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
                        pass

            # после клика попробуем снова найти textarea
            box = ctx.get_by_placeholder(MSG_PLACEHOLDER)
            box_count = await box.count()
            
            if box_count == 0:
                box = ctx.locator("textarea[placeholder]")
                box_count = await box.count()

        # теперь работаем с textarea, если она есть
        try:
            await box.first.wait_for(state="visible", timeout=5_000)
        except Exception:
            return

        await box.first.fill(text)

        # Ищем кнопку Send
        send_btn = ctx.get_by_role("button", name=RE_SEND)
        send_count = await send_btn.count()
        
        if send_count == 0:
            send_btn = ctx.locator("button:has-text(/^\\s*Send\\s*$/i)")
            send_count = await send_btn.count()
            
        if send_count == 0:
            # Новые селекторы по CSS классам для Send
            send_btn = ctx.locator("button._1iRY-9hq7N_ErfzJ6CdfXn:has(span:has-text('Send'))")
            send_count = await send_btn.count()
            
        if send_count == 0:
            send_btn = ctx.locator("button:has(span._2CV_W3BKnouk-HUw1DACuL:has-text('Send'))")
            send_count = await send_btn.count()
            
        if send_count == 0:
            return
        
        # Проверяем dry_run режим
        if dry_run:
            return
            
        try:
            await send_btn.first.wait_for(state="visible", timeout=5_000)
            await send_btn.first.scroll_into_view_if_needed()
            await send_btn.first.click()
            try:
                await self.page.wait_for_load_state("networkidle", timeout=3_000)
            except Exception:
                pass
        except Exception:
            pass
            # не смогли нажать — мягко выходим
            return


    async def open_messages(self):
        # Проверяем, не находимся ли мы уже на странице сообщений
        current_url = self.page.url
        if "/pro-inbox/" in current_url:
            # Проверяем, загружен ли контент на текущей странице
            try:
                threads_container = self.page.locator("a[href^='/pro-inbox/messages/']")
                count = await threads_container.count()
                if count > 0:
                    return
                else:
                    await self.page.reload(wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass
        
        # Переходим на страницу
        await self.page.goto(f"{SETTINGS.base_url}/pro-inbox/", wait_until="domcontentloaded", timeout=15000)
        
        # Логинимся, если нужно, и снова переходим на страницу
        if "login" in self.page.url.lower():
            await self.login_if_needed()
            await self.page.goto(f"{SETTINGS.base_url}/pro-inbox/", wait_until="domcontentloaded", timeout=15000)
        
        # Ожидание загрузки React с retry логикой
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Ждем, пока корневой div (#app-page-root) наполнится контентом
                await self.page.wait_for_function(
                    "document.querySelector('#app-page-root').childElementCount > 0",
                    timeout=90000
                )

                # Ждем появления первого элемента в списке сообщений
                threads_container = self.page.locator("a[href^='/pro-inbox/messages/']")
                await threads_container.first.wait_for(timeout=15000)
                break  # Успешно загрузилось, выходим из цикла

            except PWTimeoutError:
                if attempt < max_retries - 1:
                    # Делаем refresh и ждем
                    await self.page.reload(wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(5)  # Даем время на загрузку
                else:
                    # Все попытки исчерпаны
                    await self._run_diagnostics("react_load_failure")
                    raise Exception("Could not load the messages page content after all retries. Aborting.")
    
    
    
    async def _run_diagnostics(self, failure_type: str):
        """Сохраняет диагностическую информацию при критических сбоях"""
        try:
            import os
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_dir = "/app/debug"
            os.makedirs(debug_dir, exist_ok=True)
            
            screenshot_path = f"{debug_dir}/{failure_type}_{timestamp}.png"
            await self.page.screenshot(path=screenshot_path)
            html_path = f"{debug_dir}/{failure_type}_{timestamp}.html"
            page_content = await self.page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(page_content)
            
            # Сохраняем детальную диагностику в файл
            diag_path = f"{debug_dir}/{failure_type}_{timestamp}_diagnostics.txt"
            with open(diag_path, 'w', encoding='utf-8') as f:
                f.write(f"Diagnostics for {failure_type} at {timestamp}\n")
                f.write(f"URL: {self.page.url}\n")
                f.write(f"Title: {await self.page.title()}\n")
            
            
        except Exception:
            pass  # Молча игнорируем ошибки диагностики


    async def _scroll_messages_list(self, steps: int = 3):
        panel = self.page.locator("main")
        for _ in range(steps):
            try:
                await panel.evaluate("el => el.scrollTo(0, el.scrollHeight)")
                await self.page.wait_for_timeout(300)
            except Exception:
                break


    async def get_first_thread_url_from_html(self) -> Optional[str]:
        """Извлекает URL первого треда напрямую из HTML"""
        html = await self.page.content()
        
        # Ищем все ссылки на сообщения
        pattern = re.compile(r'href="(/pro-inbox/messages/\d+)"')
        matches = pattern.findall(html)
        
        return matches[0] if matches else None


    async def _show_and_extract_in_current_thread(self) -> Optional[str]:
        """
        Extracts phone number from current lead details page (right panel).
        First tries to find visible phone numbers, then clicks "Click to show phone number" button if needed.
        Returns cleaned phone number (digits and + only) or None if not found.
        """
        
        import re
        # Ищем tel: ссылки с номером телефона в формате +1234567890 (только цифры)
        pattern = re.compile(r'href="tel:(\+\d+)"')
        html = await self.page.content()
        match = pattern.search(html)
        if match:
            phone_number = match.group(1)
            logger.info(f"DEBUG: Found phone number: {phone_number}")
            return phone_number
        else:
            logger.warning("DEBUG: Phone number not found")
            return None


    async def extract_phone(self) -> Optional[str]:
        """Извлекает телефон из первого треда (интерфейс для runner'а)"""
        # Открываем inbox
        await self.open_messages()
        
        # Получаем URL первого треда напрямую из HTML
        first_thread_url = await self.get_first_thread_url_from_html()
        logger.info(f"DEBUG: First thread URL: {first_thread_url}")
        
        if not first_thread_url:
            logger.warning("DEBUG: No first thread URL found")
            return None
        
        # Переходим на страницу треда
        await self.page.goto(f"https://www.thumbtack.com{first_thread_url}")
        logger.info(f"DEBUG: Successfully loaded thread page, final URL: {self.page.url}")
        
        # Небольшая пауза для загрузки правой панели
        await self.page.wait_for_timeout(500)
        
        # Извлекаем и возвращаем телефон
        phone = await self._show_and_extract_in_current_thread()
        return phone