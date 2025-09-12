# leadmqr/playwright_runner.py
import asyncio, threading
from typing import Dict, Any, List, Optional
from playwright.async_api import async_playwright
import redis.asyncio as aioredis
from django.conf import settings as dj_settings
import logging

from playwright_bot.config import SETTINGS
from playwright_bot.thumbtack_bot import ThumbTackBot

logger = logging.getLogger("playwright_bot")

LEASE_KEY = "tt:runner:lease"
LEASE_TTL = 30
CALL_LOCK_TTL = 120  # антидубль звонка на 2 минуты

class LeadRunner:
    def __init__(self):
        self._pw = None
        self._ctx = None
        self.leads_page = None
        self.inbox_page = None
        self.bot_leads: Optional[ThumbTackBot] = None
        self.bot_inbox: Optional[ThumbTackBot] = None
        self.stop_evt = asyncio.Event()
        self.redis = None

    async def _acquire(self) -> bool:
        return bool(await self.redis.set(LEASE_KEY, "1", ex=LEASE_TTL, nx=True))

    async def _renew(self):
        await self.redis.expire(LEASE_KEY, LEASE_TTL)

    async def start(self):
        self.redis = await aioredis.from_url(dj_settings.REDIS_URL, decode_responses=True)
        if not await self._acquire():
            logger.info("LeadRunner: lease exists, skip start")
            return

        logger.info("LeadRunner: starting playwright context")
        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=SETTINGS.user_data_dir,
            headless=False, slow_mo=0,
            args=getattr(SETTINGS, "chromium_args", ["--no-sandbox"]),
            viewport=None,
        )

        # две вкладки — держим открытыми
        self.leads_page = await self._ctx.new_page()
        await self.leads_page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=60000)

        self.inbox_page = await self._ctx.new_page()
        await self.inbox_page.goto(f"{SETTINGS.base_url}/pro-inbox/", wait_until="domcontentloaded", timeout=60000)

        self.bot_leads = ThumbTackBot(self.leads_page)
        self.bot_inbox = ThumbTackBot(self.inbox_page)

        # авто-логин при необходимости
        if "login" in self.leads_page.url.lower():
            await self.bot_leads.login_if_needed()
            await self.leads_page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=60000)
        if "login" in self.inbox_page.url.lower():
            await self.bot_inbox.login_if_needed()
            await self.inbox_page.goto(f"{SETTINGS.base_url}/pro-inbox/", wait_until="domcontentloaded", timeout=60000)

        try:
            await self._loop()
        finally:
            try:
                await self._ctx.close()
            except Exception:
                pass
            try:
                await self._pw.stop()
            except Exception:
                pass
            try:
                await self.redis.delete(LEASE_KEY)
            except Exception:
                pass
            logger.info("LeadRunner: stopped")

    async def _loop(self):
        """
        Быстрый цикл: каждые ~1–2 сек чекает новые карточки без перезапуска браузера.
        """
        last_sig = ""
        while not self.stop_evt.is_set():
            await self._renew()

            await self.bot_leads.open_leads()
            leads = await self.bot_leads.list_new_leads()
            sig = ",".join(l.get("lead_key","") for l in leads)[:256]
            logger.info("LeadRunner: leads=%s", [l.get("lead_key") for l in leads])

            if leads and sig != last_sig:
                lead = leads[0]
                try:
                    # 1) отправляем сообщение
                    await self.bot_leads.open_lead_details(lead)
                    await self.bot_leads.send_template_message(dry_run=False)

                    # 2) ждём, пока номер проявится в Inbox (до ~2 сек, если надо)
                    phones = await self._try_fetch_phone_with_retry(attempts=3, delay=0.7)
                    logger.info("LeadRunner: phones=%s", [(p.get("lead_key"), p.get("phone")) for p in phones])

                    # 3) сохраняем и триггерим звонок
                    await self._persist_and_call(leads=[lead], phones=phones)
                except Exception as e:
                    logger.exception("LeadRunner loop error: %s", e)
                last_sig = sig

            await asyncio.sleep(1.2 if leads else 1.8)

    async def _try_fetch_phone_with_retry(self, attempts=3, delay=0.7):
        phones: List[Dict[str, Any]] = []
        for _ in range(attempts):
            phones = await self.bot_inbox.extract_phones_from_all_threads()
            if any(x.get("phone") for x in phones):
                break
            await asyncio.sleep(delay)
        return phones

    async def _persist_and_call(self, *, leads: List[Dict[str, Any]], phones: List[Dict[str, Any]]):
        """
        Сохраняем обработанные лиды, телефоны и сразу шлём задачу на звонок.
        """
        from asgiref.sync import sync_to_async
        from leads.models import FoundPhone, ProcessedLead
        from ai_calls.tasks import enqueue_ai_call

        # помечаем лиды
        for l in leads or []:
            lk = l.get("lead_key")
            if not lk:
                continue
            await sync_to_async(ProcessedLead.objects.get_or_create)(key=lk)

        # сохраняем телефоны и шлём звонок
        for p in (phones or []):
            lk, ph = p.get("lead_key"), p.get("phone")
            if not (lk and ph):
                continue

            # антидубль на короткое окно
            dedup_key = f"ai:call:lock:{lk}:{ph}"
            locked = await self.redis.set(dedup_key, "1", ex=CALL_LOCK_TTL, nx=True)
            if not locked:
                logger.info("LeadRunner: skip duplicate call within TTL for %s %s", lk, ph)
                continue

            vars_item = dict(
                source="thumbtack",
                lead_key=lk,
                lead_url=f"{SETTINGS.base_url}{p.get('href','')}",
            )
            if p.get("variables"):
                vars_item.update(p["variables"])

            phone_obj, _ = await sync_to_async(FoundPhone.objects.get_or_create)(
                lead_key=lk, phone=ph, defaults={"variables": vars_item}
            )
            logger.info("LeadRunner: enqueue_ai_call lead=%s phone=%s", lk, ph)
            enqueue_ai_call.delay(str(phone_obj.id))


# ---- фоновый стартер для Celery-воркера ----

_runner_thread: Optional[threading.Thread] = None

def _thread_target():
    asyncio.run(LeadRunner().start())

def start_runner_in_background() -> bool:
    global _runner_thread
    if _runner_thread and _runner_thread.is_alive():
        return False
    _runner_thread = threading.Thread(target=_thread_target, name="LeadRunnerThread", daemon=True)
    _runner_thread.start()
    return True