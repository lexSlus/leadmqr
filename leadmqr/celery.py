import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "leadmqr.settings")

app = Celery("leadmqr")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()  # подтягивает tasks из INSTALLED_APPS