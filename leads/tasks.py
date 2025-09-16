import asyncio
import logging
import threading

from typing import Dict, Any

from celery import shared_task
from django.core.cache import cache

from ai_calls.tasks import enqueue_ai_call

from leadmqr.celery import app
from leads.models import FoundPhone, ProcessedLead
from playwright_bot.playwright_runner import LeadRunner
# from playwright_bot.workflows import run_single_pass

logger = logging.getLogger("playwright_bot")


# LOCK_KEY = "scan_leads_lock"
# LOCK_TTL = 60 * 10

# @app.task(queue="crawler")
# def poll_leads() -> Dict[str, Any]:
#     if not cache.add(LOCK_KEY, "1", LOCK_TTL):
#         return {"ok": False, "skipped": "locked"}
#     try:
#         result: Dict[str, Any] = asyncio.run(run_single_pass())
#
#         for p in result.get("phones", []) or []:
#             lk, ph = p.get("lead_key"), p.get("phone")
#             vars_item = p.get("variables", {})
#             if lk and ph:
#                 phone_obj, _ = FoundPhone.objects.get_or_create(
#                     lead_key=lk,
#                     phone=ph,
#                     defaults={"variables": vars_item}
#                 )
#                 enqueue_ai_call.delay(str(phone_obj.id))
#         for item in result.get("sent", []) or []:
#             lk = item.get("lead_key")
#             if lk and (item.get("status") or "").startswith("sent"):
#                 ProcessedLead.objects.get_or_create(key=lk)
#
#         return result
#     finally:
#         cache.delete(LOCK_KEY)

_runner = None
_runner_loop_id = None

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

@shared_task(queue="lead_proc")
def process_single_lead_task(lead: dict, need_phone: bool = True) -> dict:
    """
    Целерий-таска: обработка ОДНОГО лида.
    - Использует LeadRunner для отправки шаблона Thumbtack
    - Если phone найден → ставим звонок
    - Возвращаем словарь результата
    """

    async def _run():
        runner = await _get_runner()
        result = await runner.process_lead(lead, need_phone=need_phone)

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
            enqueue_ai_call.delay(str(phone_obj.id))
            logger.info("Lead %s: телефон %s — отправлен на звонок", lk, ph)
        return result

    return asyncio.run(_run())