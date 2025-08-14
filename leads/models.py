
from django.db import models


class FoundPhone(models.Model):
    lead_key = models.CharField(max_length=64, db_index=True)  # md5 хэш URL лида
    phone = models.CharField(max_length=32, db_index=True)     # телефон в чистом виде
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("lead_key", "phone")
        verbose_name = "Найденный телефон"
        verbose_name_plural = "Найденные телефоны"

    def __str__(self):
        return f"{self.phone} ({self.lead_key})"


class ProcessedLead(models.Model):
    key = models.CharField(max_length=64, unique=True, db_index=True)  # md5 хэш URL лида
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Обработанный лид"
        verbose_name_plural = "Обработанные лиды"

    def __str__(self):
        return self.key