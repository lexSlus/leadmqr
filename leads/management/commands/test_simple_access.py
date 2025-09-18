from django.core.management.base import BaseCommand
import asyncio
import os
from playwright_bot.simple_runner import test_simple_access


class Command(BaseCommand):
    help = 'Test simple access to Thumbtack without stealth mode'

    def handle(self, *args, **options):
        # Проверяем есть ли DISPLAY для GUI
        if not os.getenv('DISPLAY'):
            self.stdout.write("⚠️  No DISPLAY found, using headless mode")
            
        result = asyncio.run(test_simple_access())
        self.stdout.write(f"Final URL: {result}")
        
        if "login" in result.lower():
            self.stdout.write(self.style.ERROR("❌ Still redirected to login"))
            self.stdout.write("💡 Try: docker compose exec web python manage.py setup_thumbtack_profile")
        else:
            self.stdout.write(self.style.SUCCESS("✅ Successfully accessed pro-leads!"))
