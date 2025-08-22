import asyncio

from typing import Dict, Any
from django.core.cache import cache

from ai_calls.tasks import enqueue_ai_call

from leadmqr.celery import app
from leads.models import FoundPhone, ProcessedLead
from playwright_bot.workflows import run_single_pass


LOCK_KEY = "scan_leads_lock"
LOCK_TTL = 60 * 10

@app.task(queue="crawler")
def poll_leads() -> Dict[str, Any]:
    if not cache.add(LOCK_KEY, "1", LOCK_TTL):
        return {"ok": False, "skipped": "locked"}
    try:
        result: Dict[str, Any] = asyncio.run(run_single_pass())

        for p in result.get("phones", []) or []:
            lk, ph = p.get("lead_key"), p.get("phone")
            if lk and ph:
                phone_obj, _ = FoundPhone.objects.get_or_create(lead_key=lk, phone=ph)
                enqueue_ai_call.delay(str(phone_obj.id))
        for item in result.get("sent", []) or []:
            lk = item.get("lead_key")
            if lk and (item.get("status") or "").startswith("sent"):
                ProcessedLead.objects.get_or_create(key=lk)

        return result
    finally:
        cache.delete(LOCK_KEY)

