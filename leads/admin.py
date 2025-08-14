
from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import FoundPhone, ProcessedLead


@admin.register(FoundPhone)
class FoundPhoneAdmin(ModelAdmin):
    list_display = ("phone", "lead_key", "created_at")
    list_filter = ("created_at",)
    search_fields = ("phone", "lead_key")
    ordering = ("-created_at",)


@admin.register(ProcessedLead)
class ProcessedLeadAdmin(ModelAdmin):
    list_display = ("key", "created_at")
    list_filter = ("created_at",)
    search_fields = ("key",)
    ordering = ("-created_at",)