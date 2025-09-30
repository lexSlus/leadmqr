# playwright_bot/lead_producer.py
import asyncio, logging
from typing import Optional, Dict, Any, List
import redis.asyncio as aioredis
from django.conf import settings as dj_settings
from playwright.async_api import async_playwright
from celery import current_app as celery_app

from playwright_bot.config import SETTINGS
from playwright_bot.thumbtack_bot import ThumbTackBot
from playwright_bot.utils import unique_user_data_dir, FlowTimer


log = logging.getLogger("playwright_bot")

HEARTBEAT_KEY = "tt:runner:hb"
HEARTBEAT_TTL = 15
LEASE_KEY     = "tt:runner:lease"
LEASE_TTL     = 30
ENQ_TTL       = 90

class LeadProducer:
    def __init__(self):
        self._pw = None
        self._ctx = None
        self.page = None
        self.bot: Optional[ThumbTackBot] = None
        self.stop_evt = asyncio.Event()
        self.redis: Optional[aioredis.Redis] = None
        self.user_dir = SETTINGS.user_data_dir  # Используем фиксированную директорию как в run_single_pass
        self.flow = FlowTimer(redis_url=dj_settings.REDIS_URL)
        self.sent_leads = set()  # Кэш отправленных лидов для предотвращения дубликатов

    async def _acquire(self) -> bool:
        return bool(await self.redis.set(LEASE_KEY, "1", ex=LEASE_TTL, nx=True))

    async def _renew(self):  await self.redis.expire(LEASE_KEY, LEASE_TTL)
    async def _hb(self):     await self.redis.set(HEARTBEAT_KEY, "1", ex=HEARTBEAT_TTL)
    


    async def start(self):
        self.redis = await aioredis.from_url(dj_settings.REDIS_URL, decode_responses=True)
        if not await self._acquire():
            log.info("LeadProducer: lease exists, skip")
            return

        self._pw = await async_playwright().start()
        
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=self.user_dir,
            headless=False,  # Используем Xvfb для Docker
            args=[
                "--start-maximized",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-features=VizDisplayCompositor",
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--disable-plugins",
            ],
            viewport=None,
        )
        self.page = await self._ctx.new_page()
        
        # Блокируем ненужные ресурсы для ускорения и добавляем заголовки против кеширования
        async def handle_route(route):
            if route.request.resource_type in ["image", "font", "media"]:
                await route.abort()
            else:
                # Добавляем заголовки против кеширования для API запросов
                headers = route.request.headers
                if "api" in route.request.url or "leads" in route.request.url:
                    headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                    headers["Pragma"] = "no-cache"
                    headers["Expires"] = "0"
                await route.continue_(headers=headers)
        
        await self.page.route("**/*", handle_route)
        
        self.bot = ThumbTackBot(self.page)
        
        # Сначала пытаемся открыть страницу лидов
        await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=10000)
        log.info("LeadProducer: opened %s (url=%s)", "/pro-leads", self.page.url)

        # Если нас редиректнуло на логин — авторизуемся
        if "login" in self.page.url.lower():
            log.info("LeadProducer: redirected to login, authenticating...")
            await self.bot.login_if_needed()
            # После логина снова идем на страницу лидов
            await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=10000)
            log.info("LeadProducer: after login, opened %s (url=%s)", "/pro-leads", self.page.url)

        # Сохраняем состояние аутентификации
        try:
            import os
            storage_state_path = "pw_profiles/auth_state.json"
            os.makedirs("pw_profiles", exist_ok=True)
            await self._ctx.storage_state(path=storage_state_path)
            log.info(f"Authentication state saved to {storage_state_path}")
        except Exception as e:
            log.warning(f"Could not save auth state: {e}")

        try:
            await self._loop()
        finally:
            try: await self._ctx.close()
            except: pass
            try: await self._pw.stop()
            except: pass
            try: await self.redis.delete(LEASE_KEY)
            except: pass
            log.info("LeadProducer stopped")

    async def _loop(self):
        cycle_count = 0
        while not self.stop_evt.is_set():
            try:
                cycle_count += 1
                await self._renew()
                await self._hb()
                

                # Проверяем, что браузер еще открыт
                if self.page.is_closed():
                    log.error("LeadProducer[cycle=%d]: browser closed, stopping", cycle_count)
                    break

                # Принудительно перезагружаем страницу для обновления кэша (hard reload)
                await self.page.evaluate("() => { window.location.reload(true); }")
                # Ждем только базовую загрузку, не networkidle (React может загружаться долго)
                await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
                log.info("LeadProducer[cycle=%d]: hard reloaded page for fresh content", cycle_count)
                
                # Открываем страницу лидов с детальным логированием
                log.info("LeadProducer[cycle=%d]: opening /leads page...", cycle_count)
                await self.bot.open_leads()
                log.info("LeadProducer[cycle=%d]: opened /leads (url=%s)", cycle_count, self.page.url)
                
                # Проверяем авторизацию - если редиректнуло на логин, переавторизуемся
                if "login" in self.page.url.lower():
                    log.warning("LeadProducer[cycle=%d]: redirected to login, re-authenticating...", cycle_count)
                    await self.bot.login_if_needed()
                    await self.bot.open_leads()
                    log.info("LeadProducer[cycle=%d]: re-authenticated, current URL: %s", cycle_count, self.page.url)
                
                # Проверяем что страница загрузилась корректно
                try:
                    page_title = await self.page.title()
                    log.info("LeadProducer[cycle=%d]: page title: %s", cycle_count, page_title)
                except Exception as e:
                    log.warning("LeadProducer[cycle=%d]: failed to get page title: %s", cycle_count, e)
                
                # Ищем лиды с детальным логированием
                log.info("LeadProducer[cycle=%d]: searching for leads...", cycle_count)
                leads: List[Dict[str, Any]] = await self.bot.list_new_leads()
                log.info("LeadProducer[cycle=%d]: found %d leads", cycle_count, len(leads))
                
                # Детальная информация о найденных лидах
                if leads:
                    for i, lead in enumerate(leads):
                        log.info("LeadProducer[cycle=%d]: lead[%d]: key=%s, name=%s, category=%s", 
                                cycle_count, i, lead.get('lead_key'), lead.get('name'), lead.get('category'))
                else:
                    log.warning("LeadProducer[cycle=%d]: no leads found - checking page content...", cycle_count)
                    # Проверяем содержимое страницы для отладки
                    try:
                        page_content = await self.page.content()
                        log.info("LeadProducer[cycle=%d]: page content length: %d chars", cycle_count, len(page_content))
                        # Проверяем есть ли элементы лидов на странице
                        lead_elements = await self.page.locator('[data-testid*="lead"], .lead, [class*="lead"]').count()
                        log.info("LeadProducer[cycle=%d]: found %d potential lead elements on page", cycle_count, lead_elements)
                    except Exception as e:
                        log.warning("LeadProducer[cycle=%d]: failed to analyze page content: %s", cycle_count, e)
                
                processed_count = 0
                for lead in leads:
                    lk = lead.get("lead_key")
                    if not lk:
                        log.warning("LeadProducer[cycle=%d]: skip lead without lead_key: %s", cycle_count, lead)
                        continue

                    if lk in self.sent_leads:
                        log.info("LeadProducer[cycle=%d]: skip already sent lead %s", cycle_count, lk)
                        continue

                    self.flow.mark(lk, "detect")
                    
                    # Отправляем в очередь на обработку
                    celery_app.send_task(
                        "leads.tasks.process_lead_task",
                        args=[lead],
                        queue="lead_proc",
                        retry=False,
                    )
                    self.sent_leads.add(lk)
                    processed_count += 1
                    log.info("LeadProducer[cycle=%d]: enqueued lead %s", cycle_count, lk)

                log.info("LeadProducer[cycle=%d]: processed %d/%d leads", cycle_count, processed_count, len(leads))
                
                # Адаптивная задержка: если есть лиды - ждем дольше, чтобы LeadRunner успел обработать
                delay = 10.0 if leads else 30.0  # 10 секунд если есть лиды, 30 секунд если нет
                await asyncio.sleep(delay)
                
            except Exception as e:
                log.error("LeadProducer[cycle=%d]: error in main loop: %s", cycle_count, e, exc_info=True)
                await asyncio.sleep(5.0)  # Больше задержка при ошибке
