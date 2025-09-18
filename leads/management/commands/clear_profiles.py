from django.core.management.base import BaseCommand
import os
import shutil
import subprocess
import logging

logger = logging.getLogger("playwright_bot")

class Command(BaseCommand):
    help = 'Clear all browser profiles and lock files'

    def handle(self, *args, **options):
        self.stdout.write("Clearing browser profiles...")
        
        # Список профилей для очистки
        profile_dirs = [
            "/app/tt_profile",
            "/app/playwright_bot/tt_profile", 
            "/app/playwright_bot/playwright_profile",
            "/app/pw_profiles"
        ]
        
        for profile_dir in profile_dirs:
            if os.path.exists(profile_dir):
                try:
                    # Проверяем используется ли профиль
                    result = subprocess.run(['lsof', profile_dir], capture_output=True, text=True)
                    if result.returncode == 0 and result.stdout:
                        self.stdout.write(f"Profile {profile_dir} is in use, killing processes...")
                        # Убиваем процессы использующие профиль
                        subprocess.run(['pkill', '-f', profile_dir], capture_output=True)
                        import time
                        time.sleep(2)
                    
                    # Удаляем профиль
                    if os.path.isdir(profile_dir):
                        shutil.rmtree(profile_dir)
                        self.stdout.write(f"Removed directory: {profile_dir}")
                    else:
                        os.remove(profile_dir)
                        self.stdout.write(f"Removed file: {profile_dir}")
                        
                except Exception as e:
                    self.stdout.write(f"Error removing {profile_dir}: {e}")
        
        # Убиваем все процессы Chrome/Chromium
        try:
            subprocess.run(['pkill', '-f', 'chrome'], capture_output=True)
            subprocess.run(['pkill', '-f', 'chromium'], capture_output=True)
            self.stdout.write("Killed Chrome/Chromium processes")
        except Exception as e:
            self.stdout.write(f"Error killing processes: {e}")
        
        self.stdout.write(self.style.SUCCESS("Profile cleanup completed!"))
