from leads.models import FoundPhone
from .services import AICallService
from leadmqr.celery import app
import logging

logger = logging.getLogger("playwright_bot")

@app.task(queue='ai_calls.enqueue_ai_call')
def enqueue_ai_call(found_phone_id: str):
    phone_obj = FoundPhone.objects.get(id=found_phone_id)
    logger.info("AI call: lead_key=%s, phone=%s", phone_obj.lead_key, phone_obj.phone)
    ai_service = AICallService()
    call = ai_service.enqueue_if_needed(
        lead_key=phone_obj.lead_key,
        phone=phone_obj.phone,
    )
    if not call:
        logger.error("AI call skipped")
        return {"skepped": True}
    resp = ai_service.start_call(call)
    logger.info("AI call started %s", resp)
    return resp