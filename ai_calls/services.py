from typing import Dict, Any, Optional
from django.db import transaction
from django.conf import settings
from .client import VocalyClient
from .models import AICall



class AICallService:
    def __init__(self):
        self.client = VocalyClient()

    @transaction.atomic
    def enqueue_if_needed(self, *, lead_key: str, phone: str) -> Optional[AICall]:
        # не плодим дублей, если уже ждём/в процессе по этому lead_key+phone
        exists = AICall.objects.filter(
            lead_key=lead_key,
            to_phone=phone,
            status__in=[AICall.Status.PENDING, AICall.Status.IN_PROGRESS],
        ).exists()
        if exists:
            return None

        call = AICall.objects.create(
            lead_key=lead_key,
            to_phone=phone,
            status=AICall.Status.PENDING,
        )
        return call


    def start_call(self, call: AICall, variables: dict | None = None)-> Dict[str, Any]:
        to_phone_number = call.to_phone
        variables = variables or {}

        payload = {
            "fromPhoneNumber": settings.FROM_PHONE_NUMBER,
            "toPhoneNumber": to_phone_number,
            "variables": variables,
            "settings": {
                "timeZone": call.user_timezone,
            }
        }

        with transaction.atomic():
            call.status = AICall.Status.IN_PROGRESS
            call.request_payload = payload
            call.save(update_fields=["status","request_payload","updated_at"])

        resp = self.client.create_call(
            agent_id=settings.AGENT_ID,
            from_number=settings.FROM_PHONE_NUMBER,
            to_number=to_phone_number,
            variables=variables,

        )
        call.provider_call_id = str(resp.get("id") or resp.get("providerCallID") or "")
        call.response_payload = resp
        call.save(update_fields=["provider_call_id","response_payload","updated_at"])
        return resp