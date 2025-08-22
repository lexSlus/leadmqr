from leads.models import FoundPhone
from .services import AICallService
from leadmqr.celery import app


@app.task(queue='ai_calls.enqueue_ai_call')
def enqueue_ai_call(found_phone_id: str):
    phone_obj = FoundPhone.objects.get(id=found_phone_id)
    ai_service = AICallService()
    call = ai_service.enqueue_if_needed(
        lead_key=phone_obj.lead_key,
        phone=phone_obj.phone,
    )
    if call:
        ai_service.start_call(call)

