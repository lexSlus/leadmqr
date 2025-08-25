from typing import Dict, Any

from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ai_calls.models import AICall
from django.conf import settings
from ai_calls.utils import verify_vocaly_signature
import logging

logger = logging.getLogger('playwright_bot')

class VocalyaiWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        secret = getattr(settings, "VOCALY_WEBHOOK_SECRET", None)
        signature = request.headers.get("X-Webhook-Signature") or request.headers.get("Signature")
        if secret and not verify_vocaly_signature(secret, request.body or b"", signature):
            return Response({"detail": "invalid signature"}, status=status.HTTP_403_FORBIDDEN)

        payload: Dict[str, Any] = request.data if isinstance(request.data, dict) else {}
        logger.info(f'payload- {payload}')
        call_data: Dict[str, Any] = payload.get("call") or {}
        provider_call_id = call_data.get("id")
        analytics = call_data.get("analytics") or {}
        vars_dict = {}
        if "callVariables" in analytics:
            vars_dict.update(analytics["callVariables"])
        if "customJSONAnalytics" in analytics:
            vars_dict.update(analytics["customJSONAnalytics"])

        if not provider_call_id:
            return Response({"detail": "no call id in payload"}, status=status.HTTP_400_BAD_REQUEST)

        call = AICall.objects.filter(provider_call_id=str(provider_call_id)).first()
        if not call:
            return Response({"detail": "call not found"}, status=status.HTTP_202_ACCEPTED)

        # обновляем статус, длительность и весь вебхук
        call.status = call_data.get("status") or call.status
        call.duration_sec = call_data.get("duration") or call.duration_sec
        call.webhook_payload = payload
        call.agreed_address = vars_dict.get("address")
        call.agreed_contact_phone = vars_dict.get("contact_phone_number")
        call.agreed_datetime = vars_dict.get("desired_date_and_time")
        call.save(update_fields=[
            "status",
            "duration_sec",
            "webhook_payload",
            "updated_at",
            "agreed_address",
            "agreed_contact_phone",
            "agreed_datetime"
        ])

        logger.info("[Vocaly Webhook] call updated", extra={
            "provider_call_id": provider_call_id,
            "status": call.status,
            "duration": call.duration_sec,
        })
        return Response({"detail": "ok"}, status=status.HTTP_200_OK)