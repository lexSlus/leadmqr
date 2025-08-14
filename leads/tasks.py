import asyncio

from celery import shared_task
from typing import Dict, Any, List
from django.core.cache import cache
from playwright.async_api import async_playwright

from leads.models import FoundPhone, ProcessedLead
from playwright_bot.workflows import run_single_pass


# @shared_task
# def poll_leads():
#     result = run_until_leads()
#     print(f"[BOT RESULT] {result}")
#     return result


LOCK_KEY = "scan_leads_lock"
LOCK_TTL = 60 * 10

@shared_task()
def poll_leads() -> Dict[str, Any]:
    if not cache.add(LOCK_KEY, "1", LOCK_TTL):
        return {"ok": False, "skipped": "locked"}
    try:
        result: Dict[str, Any] = asyncio.run(run_single_pass(headless=True))

        for p in result.get("phones", []) or []:
            lk, ph = p.get("lead_key"), p.get("phone")
            if lk and ph:
                FoundPhone.objects.get_or_create(lead_key=lk, phone=ph)

        for item in result.get("sent", []) or []:
            lk = item.get("lead_key")
            if lk and (item.get("status") or "").startswith("sent"):
                ProcessedLead.objects.get_or_create(key=lk)

        return result
    finally:
        cache.delete(LOCK_KEY)
