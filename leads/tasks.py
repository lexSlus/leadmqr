import asyncio
import logging
import time
from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from ai_calls.tasks import enqueue_ai_call
from leads.models import FoundPhone, ProcessedLead
from playwright_bot.playwright_runner import LeadRunner
from playwright_bot.utils import FlowTimer

logger = logging.getLogger("playwright_bot")
flow = FlowTimer()

_runner = None
_runner_loop_id = None

# Rate limiting для защиты от блокировки Thumbtack
RATE_LIMIT_KEY = "thumbtack_rate_limit"
RATE_LIMIT_INTERVAL = 1.0  # 1 секунда между запросами

# Кэширование найденных телефонов для ускорения
PHONE_CACHE_KEY = "found_phone_cache"
PHONE_CACHE_TIMEOUT = 3600  # 1 час кэш

async def wait_for_rate_limit():
    """Ожидает соблюдения rate limit (1 запрос в секунду)"""
    while True:
        last_request_time = cache.get(RATE_LIMIT_KEY, 0)
        current_time = time.time()
        
        if current_time - last_request_time >= RATE_LIMIT_INTERVAL:
            # Можно делать запрос
            cache.set(RATE_LIMIT_KEY, current_time, timeout=10)
            logger.debug("Rate limit: разрешен запрос (последний: %.2f сек назад)", 
                        current_time - last_request_time)
            return
        
        # Нужно подождать
        wait_time = RATE_LIMIT_INTERVAL - (current_time - last_request_time)
        logger.debug("Rate limit: ожидание %.2f сек до следующего запроса", wait_time)
        await asyncio.sleep(wait_time)

async def _get_runner() -> LeadRunner:
    global _runner, _runner_loop_id
    loop = asyncio.get_running_loop()
    loop_id = id(loop)

    need_new = (_runner is None) or (_runner_loop_id != loop_id)
    if need_new:
        if _runner is not None:
            try:
                await _runner.close()
            except Exception:
                pass
        _runner = LeadRunner()
        await _runner.start()
        _runner_loop_id = loop_id
    return _runner

@shared_task(name="leads.tasks.process_lead_task", queue="lead_proc", bind=True)
def process_single_lead_task(self, lead: dict) -> dict:
    """
    Целерий-таска: обработка ОДНОГО лида.
    - Использует LeadRunner для отправки шаблона Thumbtack
    - Если phone найден → ставим звонок
    - Возвращаем словарь результата
    """

    async def _run():
        # Соблюдаем rate limit перед обработкой лида
        await wait_for_rate_limit()
        
        runner = await _get_runner()
        result = await runner.process_lead(lead)

        lk = result.get("lead_key")
        ph = result.get("phone")
        vars_item = result.get("variables", {})
        if lk:
            await asyncio.to_thread(ProcessedLead.objects.get_or_create, key=lk)

        if lk and ph:
            phone_obj, _ = await asyncio.to_thread(
                FoundPhone.objects.get_or_create,
                lead_key=lk,
                phone=ph,
                defaults={"variables": vars_item},
            )
            enqueue_ai_call.apply_async(args=[str(phone_obj.id)], queue="ai_calls")
            flow.mark(lk, "call_started")
            logger.info("Lead %s: телефон %s — отправлен на звонок", lk, ph)
        return result

    return asyncio.run(_run())