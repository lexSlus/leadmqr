from django.utils import timezone
from uuid import uuid4
from django.db import models


class AICall(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In progress"
        FINISHED = "finished", "Finished"
        ERROR = "error", "Error"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    to_phone = models.CharField(max_length=32)
    from_phone = models.CharField(max_length=32, blank=True, null=True)
    agent_id = models.CharField(max_length=128)
    user_timezone = models.CharField(max_length=64, default="America/New_York")
    duration_sec = models.PositiveIntegerField(blank=True, null=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    provider_call_id = models.CharField(max_length=128, blank=True, null=True, db_index=True)

    variables = models.JSONField(default=dict, blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    webhook_payload = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now())
    updated_at = models.DateTimeField(auto_now=True)