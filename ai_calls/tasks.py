from leads.models import FoundPhone
from .services import AICallService
from celery import shared_task
import logging

logger = logging.getLogger("playwright_bot")

@shared_task(name="ai_calls.tasks.enqueue_ai_call", queue="ai_calls")
def enqueue_ai_call(found_phone_id: str):
    phone_obj = FoundPhone.objects.get(id=found_phone_id)
    logger.info("AI call: lead_key=%s, phone=%s", phone_obj.lead_key, phone_obj.phone)
    ai_service = AICallService()
    call = ai_service.enqueue_if_needed(
        lead_key=phone_obj.lead_key,
        phone=phone_obj.phone,
    )
    # Убрали проверку call для тестирования - всегда делаем звонок
    # if not call:
    #     logger.error("AI call skipped")
    #     return {"skipped": True}
    resp = ai_service.start_call(call, variables=phone_obj.variables)
    logger.info("AI call started %s", resp)
    return resp