from django.urls import path
from ai_calls.views import VocalyaiWebhookView  # поправь импорт под свой модуль

urlpatterns = [

    path("webhooks/vocaly/", VocalyaiWebhookView.as_view(), name="vocaly-webhook"),
]