import asyncio
import logging

from typing import Dict, Any
from django.core.cache import cache
from ai_calls.tasks import enqueue_ai_call
from telegram_app.tasks import send_telegram_notification_task

from celery import shared_task
from leads.models import FoundPhone, ProcessedLead
from telegram_app.telegram_message import send_telegram_message

logger = logging.getLogger("playwright_bot")
from playwright_bot.workflows import run_single_pass
from playwright_bot.playwright_runner import LeadRunner


LOCK_KEY = "scan_leads_lock"
LOCK_TTL = 60 * 2

# @shared_task(queue="crawler")
# def poll_leads() -> Dict[str, Any]:
#     if not cache.add(LOCK_KEY, "1", LOCK_TTL):
#         return {"ok": False, "skipped": "locked"}
#     try:
#         result: Dict[str, Any] = asyncio.run(run_single_pass())

#         for p in result.get("phones", []) or []:
#             lk, ph = p.get("lead_key"), p.get("phone")
#             variables = p.get("variables", {})
#             if lk and ph:
#                 phone_obj, _ = FoundPhone.objects.get_or_create(
#                     lead_key=lk,
#                     phone=ph,
#                     defaults={"variables": variables}
#                 )
                
#                 # enqueue_ai_call.delay(str(phone_obj.id))
#         for item in result.get("sent", []) or []:
#             lk = item.get("lead_key")
#             if lk and (item.get("status") or "").startswith("sent"):
#                 ProcessedLead.objects.get_or_create(key=lk)

#         return result
#     finally:
#         cache.delete(LOCK_KEY)


@shared_task(queue="lead_proc")
def process_lead_task(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обработка одного лида через LeadRunner.
    Вызывается LeadProducer'ом когда найден новый лид.
    """
    lk = lead.get("lead_key", "unknown")
    logger.info("process_lead_task: starting processing for lead %s", lk)

    # Создаем вложенную async функцию, чтобы управлять всем в одном цикле
    async def main():
        runner = LeadRunner()
        try:
            # Выполняем основную работу
            return await runner.process_lead(lead)
        finally:
            # Гарантированно закрываем runner в том же цикле, где он работал
            logger.info("process_lead_task: closing runner for lead %s", lk)
            await runner.close()

    try:
        # Запускаем всю async логику ОДНИМ вызовом asyncio.run()
        result = asyncio.run(main())

        # --- Дальнейшая обработка результата (уже в синхронном коде) ---
        if result.get("ok"):
            if result.get("phone"):
                logger.info("process_lead_task: phone found for %s, creating FoundPhone", lk)
                
                # Если найден телефон, создаем FoundPhone и запускаем AI call
                phone_obj, created = FoundPhone.objects.get_or_create(
                    lead_key=result["lead_key"],
                    phone=result["phone"],
                    defaults={"variables": result["variables"]}
                )
                
                logger.info("process_lead_task: FoundPhone %s for lead %s (created=%s)", 
                           phone_obj.id, lk, created)
                
                # Запускаем AI call
                # enqueue_ai_call.delay(str(phone_obj.id))
                # logger.info("process_lead_task: enqueued AI call for lead %s", lk)
                variables = result.get("variables", {})
                message = (f"🚨 <b>New Lead Ready for Call!</b>\n"
                           f"👤 <b>Client:</b> {variables.get("name", "Unknown")}\n"
                           f"🏠 <b>Category:</b> {variables.get("category", "Unknown")}\n"
                           f"📍 <b>Location:</b> {variables.get("location", "Unknown")}\n"
                           f"📞 <b>PHONE:</b> <code>{result.get("phone", "Unknown")}</code>\n"
                           f'🔗 <b>Link:</b> <a href="{variables.get("lead_url", "")}">Open Lead</a>')

                result = send_telegram_message(
                    "8461859680:AAG2ZfcXkUd9Z69l53ks2P6BYD3yH_xFyIs",
                    -1003020610250,
                    message,
                )
                
            else:
                logger.warning("process_lead_task: no phone found for lead %s", lk)
            
            # Отмечаем лид как обработанный
            ProcessedLead.objects.get_or_create(key=result["lead_key"])
            logger.info("process_lead_task: marked lead %s as processed", lk)
            
        else:
            logger.error("process_lead_task: failed to process lead %s: %s", 
                        lk, result.get("error", "unknown error"))
        
        return result
        
    except Exception as e:
        logger.error("process_lead_task: critical error processing lead %s: %s", lk, e, exc_info=True)
        return {"ok": False, "error": str(e), "lead": lead}

