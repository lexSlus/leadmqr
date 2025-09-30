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


    async def _threads(self):
        # Проверяем состояние страницы перед поиском тредов
        try:
            # Проверяем, что мы на правильной странице
            if "/pro-inbox/" not in self.page.url:
                return self.page.locator("a[href^='/pro-inbox/messages/']")  # Возвращаем пустой locator
            
            # Проверяем, что React загрузился
            app_root = await self.page.evaluate("document.querySelector('#app-page-root')?.childElementCount || 0")
            
            if app_root == 0:
                await self.page.wait_for_function(
                    "document.querySelector('#app-page-root').childElementCount > 0",
                    timeout=10000
                )
            
        except Exception:
            pass
        
        # Список селекторов для поиска тредов (от наиболее специфичных к менее)
        selectors = [
            "a[href^='/pro-inbox/messages/']",  # Основной селектор
            "a[href*='/pro-inbox/messages/']",  # Более широкий поиск
            "main a[href*='messages']",         # Любые ссылки в main
            "[data-testid*='message'] a",       # По data-testid
            "[data-testid*='thread'] a",        # Альтернативный data-testid
            "a[href*='messages']",              # Еще более широкий поиск
            ".message-item a",                  # По классу
            "[role='listitem'] a",              # По роли
            "div[class*='message'] a",          # По классу div
        ]
        
        locator = None
        count = 0
        
        for i, selector in enumerate(selectors):
            try:
                test_locator = self.page.locator(selector)
                test_count = await test_locator.count()
                
                if test_count > 0:
                    locator = test_locator
                    count = test_count
                    break
                    
            except Exception:
                continue
        
        # Если ничего не нашли, пробуем еще более агрессивные методы
        if count == 0:
            # Ищем ссылки, содержащие 'messages' в href
            message_links = self.page.locator("a[href*='messages']")
            message_count = await message_links.count()
            
            if message_count > 0:
                locator = message_links
                count = message_count
        
        # Дополнительная диагностика
        if count == 0:
            await self._run_diagnostics("no_threads_found")
        return locator


    async def _show_and_extract_in_current_thread(self) -> Optional[str]:
        """
        Extracts phone number from current lead details page (right panel).
        First tries to find visible phone numbers, then clicks "Click to show phone number" button if needed.
        Returns cleaned phone number (digits and + only) or None if not found.
        """
        
        # Method 1: Look for "Click to show phone number" button first (most common case)
        show_phone_button = self.page.locator("button:has-text('Click to show phone number')")
        button_count = await show_phone_button.count()
        
        # Try alternative selectors for phone button
        if button_count == 0:
            show_phone_button = self.page.locator("button._3HFh8Wm0kL8FRvqW7u0LOA")
            button_count = await show_phone_button.count()
            
        if button_count == 0:
            show_phone_button = self.page.locator("button[role='button']:has-text('show phone')")
            button_count = await show_phone_button.count()
            
        if button_count == 0:
            show_phone_button = self.page.locator("button:has-text('phone')")
            button_count = await show_phone_button.count()
        
        if button_count > 0:
            try:
                await show_phone_button.first.click()
                await self.page.wait_for_timeout(1000)  # Short wait for phone to appear
                
                # Try to find phone after clicking
                tel_link = self.page.locator("a[href^='tel:']")
                tel_count = await tel_link.count()
                
                if tel_count > 0:
                    try:
                        raw_href = await tel_link.first.get_attribute("href") or ""
                        phone = raw_href.replace("tel:", "")
                        if phone:
                            cleaned_phone = re.sub(r"[^\d+]", "", phone)
                            return cleaned_phone
                    except Exception as e:
                        logger.error(f"Error extracting tel href after click: {e}")
                
                # Also try text element after clicking
                phone_text_element = self.page.locator(".IUE7kXgIsvED2G8vml4Wu")
                text_count = await phone_text_element.count()
                
                if text_count > 0:
                    try:
                        phone_text = await phone_text_element.first.text_content() or ""
                        if phone_text:
                            cleaned_phone = re.sub(r"[^\d+]", "", phone_text)
                            if cleaned_phone:
                                return cleaned_phone
                    except Exception as e:
                        logger.error(f"Error extracting text content after click: {e}")
                        
            except Exception as e:
                logger.error(f"Error clicking show phone button: {e}")
        
        # Method 2: Look for tel: links (already visible)
        tel_link = self.page.locator("a[href^='tel:']")
        tel_count = await tel_link.count()
        logger.warning(f"[DEBUG] Method 2 - tel: links count: {tel_count}")
        if tel_count > 0:
            try:
                raw_href = await tel_link.first.get_attribute("href") or ""
                phone = raw_href.replace("tel:", "")
                if phone:
                    cleaned_phone = re.sub(r"[^\d+]", "", phone)
                    return cleaned_phone
            except Exception as e:
                logger.error(f"Error extracting tel href: {e}")
        
        # Method 3: Search for phone pattern in page text (with filtering)
        logger.warning("[_show_and_extract_in_current_thread] Method 3 - Searching for phone pattern in page text")
        try:
            page_text = await self.page.text_content("body")
            if page_text:
                phone_pattern = re.compile(r'\+?1?[-.\s]?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}')
                matches = phone_pattern.findall(page_text)
                logger.warning(f"[DEBUG] Method 3 - found {len(matches)} phone pattern matches")

                # Фильтруем известные системные номера Thumbtack
                excluded_phones = [
                    '5511455460',  # Thumbtack support number
                    '415-801-2000',  # Thumbtack main number
                    '4158012000',
                    '800-123-4567',  # Common placeholder numbers
                    '555-123-4567',
                    '5551234567'
                ]

                for match in matches:
                    phone = match.strip()
                    cleaned_phone = re.sub(r'[^\d+]', '', phone)

                    # Пропускаем известные системные номера
                    if cleaned_phone in excluded_phones or phone in excluded_phones:
                        logger.info(f"[_show_and_extract_in_current_thread] Method 3 - skipping known system number: {phone}")
                        continue

                    # Пропускаем номера, которые выглядят как системные (начинаются с 551, 415, 800, 555)
                    if cleaned_phone.startswith(('551', '415', '800', '555')):
                        logger.info(f"[_show_and_extract_in_current_thread] Method 3 - skipping system-like number: {phone}")
                        continue

                    logger.info(f"[_show_and_extract_in_current_thread] Method 3 - found valid phone via text pattern: {phone}")
                    return phone

                logger.warning(f"[_show_and_extract_in_current_thread] Method 3 - all {len(matches)} found phones were filtered out as system numbers")

        except Exception as e:
            logger.error(f"Error searching page text: {e}")
        
        logger.warning("[_show_and_extract_in_current_thread] No phone found using any method")
        
        # DEBUG: Сохраняем скриншот и HTML для анализа
        try:
            import os
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_dir = "/app/debug"
            os.makedirs(debug_dir, exist_ok=True)
            
            screenshot_path = f"{debug_dir}/phone_not_found_{timestamp}.png"
            await self.page.screenshot(path=screenshot_path)
            logger.warning(f"[DEBUG] Saved screenshot: {screenshot_path}")
            
            html_path = f"{debug_dir}/phone_not_found_{timestamp}.html"
            page_content = await self.page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(page_content)
            logger.warning(f"[DEBUG] Saved HTML: {html_path}")
            logger.warning(f"[DEBUG] Page URL: {self.page.url}")
        except Exception as e:
            logger.error(f"[DEBUG] Error saving debug info: {e}")
        
        return None


    async def extract_phones_from_all_threads(self, store=None) -> List[Dict[str, Any]]:
        # Пробуем открыть сообщения с retry логикой
        max_retries = 2
        for attempt in range(max_retries):
            try:
                await self.open_messages()
                break  # Успешно открыли сообщения
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)  # Небольшая пауза перед retry
                else:
                    return []  # Возвращаем пустой список при ошибке
        
        threads = await self._threads()
        total = await threads.count()

        if total == 0:
            await self._run_diagnostics("no_threads_in_extract")
            return []

        results: List[Dict[str, Any]] = []
        for i in range(total):
            try:
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

                # Прокручиваем к элементу и кликаем
                await row.scroll_into_view_if_needed()
                await self.page.wait_for_timeout(500)  # Даем время на прокрутку
                
                # Проверяем, что элемент видимый перед кликом
                try:
                    await row.wait_for(state="visible", timeout=3000)
                except Exception:
                    pass
                
                await row.click(force=True)
                
                # Ждем загрузки страницы треда
                try:
                    await self.page.wait_for_url(re.compile(r"/pro-inbox/messages/\d+"), timeout=8000)
                    await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                    await self.page.wait_for_timeout(1500)  # Даем время на полную загрузку
                except Exception as e:
                    pass

                phone = await self._show_and_extract_in_current_thread()
                
                if store is not None:
                    store.mark_thread_seen(href, phone)

                results.append({
                    "index": i,
                    "href": href,
                    "lead_key": lead_key,
                    "phone": phone,
                    "status": "processed",
                    "variables": {
                        "lead_id": lead_key,
                        "lead_url": f"https://www.thumbtack.com{href}",
                        "source": "thumbtack"
                    }
                })
                
            except Exception as e:
                # Добавляем запись об ошибке, чтобы не потерять информацию
                results.append({
                    "index": i,
                    "href": href if 'href' in locals() else "",
                    "lead_key": lead_key if 'lead_key' in locals() else "",
                    "phone": None,
                    "status": "error",
                    "error": str(e),
                    "variables": {
                        "lead_id": lead_key if 'lead_key' in locals() else "",
                        "lead_url": f"https://www.thumbtack.com{href}" if 'href' in locals() else "",
                        "source": "thumbtack"
                    }
                })

        return results