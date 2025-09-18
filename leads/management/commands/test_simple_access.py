from django.core.management.base import BaseCommand
import asyncio
from playwright_bot.simple_runner import test_simple_access


class Command(BaseCommand):
    help = 'Test simple access to Thumbtack without stealth mode'

    def handle(self, *args, **options):
        result = asyncio.run(test_simple_access())
        self.stdout.write(f"Final URL: {result}")
        
        if "login" in result.lower():
            self.stdout.write(self.style.ERROR("❌ Still redirected to login"))
        else:
            self.stdout.write(self.style.SUCCESS("✅ Successfully accessed pro-leads!"))
