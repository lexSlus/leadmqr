from typing import Dict, Any, Optional
from django.db import transaction
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


    def start_call(self, call: AICall)-> Dict[str, Any]:
        from_phone_number = call.from_phone or None
        to_phone_number = call.to_phone
        variables = call.variables or {}

        payload = {
            "fromPhoneNumber": from_phone_number,
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
            agent_id=call.agent_id,
            from_number=from_phone_number,
            to_number=to_phone_number,
            variables=variables,
            call_settings={
                "timeZone": call.user_timezone,
            }
        )
        call.provider_call_id = str(resp.get("id") or resp.get("providerCallID") or "")
        call.response_payload = resp
        call.save(update_fields=["provider_call_id","response_payload","updated_at"])
        return resp