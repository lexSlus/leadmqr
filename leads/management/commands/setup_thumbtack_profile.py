from django.core.management.base import BaseCommand
import asyncio
import os
from playwright.async_api import async_playwright


class Command(BaseCommand):
    help = 'Setup Thumbtack browser profile manually'

    def handle(self, *args, **options):
        asyncio.run(self.setup_profile())

    async def setup_profile(self):
        """Запускает браузер для ручной настройки профиля"""
        
        # Создаем профиль в tt_profile
        profile_dir = os.path.join(os.getcwd(), "tt_profile")
        os.makedirs(profile_dir, exist_ok=True)
        
        self.stdout.write(f"🔧 Настраиваем профиль в: {profile_dir}")
        self.stdout.write("🌐 Откроется браузер - войдите в Thumbtack вручную")
        self.stdout.write("📝 После успешного входа закройте браузер")
        self.stdout.write("⏳ Нажмите Enter чтобы продолжить...")
        input()
        
        async with async_playwright() as p:
            # Запускаем браузер с нашим профилем
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,  # Показываем браузер
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-images",
                    "--disable-plugins",
                    "--disable-extensions",
                ],
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            
            # Открываем Thumbtack
            page = await browser.new_page()
            await page.goto("https://www.thumbtack.com")
            
            self.stdout.write("✅ Браузер открыт!")
            self.stdout.write("🔑 Войдите в Thumbtack вручную")
            self.stdout.write("🎯 После входа закройте браузер")
            
            # Ждем пока пользователь закроет браузер
            try:
                await browser.wait_for_event("close")
            except:
                pass
                
            self.stdout.write("✅ Профиль настроен!")
