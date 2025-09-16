from django.core.management.base import BaseCommand
import asyncio
from playwright_bot.lead_producer import LeadProducer

class Command(BaseCommand):
    help = "Start LeadProducer (monitor new leads and enqueue to lead_proc)"

    def handle(self, *args, **opts):
        self.stdout.write(self.style.SUCCESS("Starting LeadProducer..."))
        asyncio.run(LeadProducer().start())