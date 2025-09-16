import asyncio
import logging
from celery import shared_task
from ai_calls.tasks import enqueue_ai_call
from leads.models import FoundPhone, ProcessedLead
from playwright_bot.playwright_runner import LeadRunner


logger = logging.getLogger("playwright_bot")


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

@shared_task(name="leads.tasks.process_lead_task", queue="lead_proc")
def process_single_lead_task(lead: dict) -> dict:
    """
    Целерий-таска: обработка ОДНОГО лида.
    - Использует LeadRunner для отправки шаблона Thumbtack
    - Если phone найден → ставим звонок
    - Возвращаем словарь результата
    """

    async def _run():
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
            enqueue_ai_call.delay(str(phone_obj.id))
            logger.info("Lead %s: телефон %s — отправлен на звонок", lk, ph)
        return result

    return asyncio.run(_run())