#!/usr/bin/env python3
"""
Скрипт для ручной настройки авторизации в Thumbtack.
Позволяет пройти капчу и сохранить сессию для автоматического использования.
"""

import os
import sys
import asyncio
import logging
from playwright.async_api import async_playwright

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright_bot.thumbtack_bot import ThumbTackBot

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AuthSetup:
    def __init__(self, headless=False):
        self.headless = headless
        self.pw = None
        self.browser = None
        self.context = None
        self.page = None
        self.bot = None
        
    async def start(self):
        """Запуск браузера для ручной авторизации"""
        logger.info("🚀 Запуск браузера для ручной авторизации...")
        
        self.pw = await async_playwright().start()
        
        # Создаем persistent context для сохранения сессии
        user_data_dir = "pw_profiles/auth_setup"
        os.makedirs(user_data_dir, exist_ok=True)
        
        self.browser = await self.pw.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=self.headless,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]
        )
        
        self.page = self.browser.pages[0] if self.browser.pages else await self.browser.new_page()
        self.bot = ThumbTackBot(self.page)
        
        logger.info("✅ Браузер запущен")
        
    async def setup_auth(self):
        """Процесс ручной авторизации"""
        logger.info("🔐 Начинаем процесс авторизации...")
        
        try:
            # Переходим на страницу логина
            logger.info("📱 Переходим на Thumbtack...")
            await self.page.goto("https://www.thumbtack.com/pro-leads")
            
            # Проверяем, нужно ли логиниться
            current_url = self.page.url
            logger.info(f"📍 Текущий URL: {current_url}")
            
            if "/login" in current_url or "login" in current_url.lower():
                logger.info("🔑 Нужна авторизация, переходим на страницу логина...")
                await self.page.goto("https://www.thumbtack.com/login")
            else:
                logger.info("✅ Уже авторизованы или на главной странице")
                
            # Ждем, пока пользователь введет данные и решит капчу
            logger.info("⏳ Ожидаем ввода данных пользователем...")
            logger.info("📝 Введите логин и пароль, решите капчу если появится")
            logger.info("🎯 После успешного входа нажмите Enter в консоли...")
            
            # Ждем подтверждения от пользователя
            try:
                input("Нажмите Enter когда авторизация будет завершена...")
            except EOFError:
                # Если input() не работает (например, в Docker), ждем 30 секунд
                logger.info("⏰ Ждем 30 секунд для завершения авторизации...")
                await asyncio.sleep(30)
            
            # Проверяем, что авторизация прошла успешно
            current_url = self.page.url
            logger.info(f"📍 URL после авторизации: {current_url}")
            
            if "/pro-leads" in current_url or "/dashboard" in current_url:
                logger.info("✅ Авторизация успешна!")
                
                # Сохраняем состояние авторизации
                await self.save_auth_state()
                
                logger.info("💾 Состояние авторизации сохранено в pw_profiles/auth_setup/")
                logger.info("🔄 Теперь LeadProducer сможет использовать эту сессию")
                
            else:
                logger.warning("⚠️ Возможно, авторизация не завершена. Проверьте URL.")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при авторизации: {e}")
            raise
            
    async def save_auth_state(self):
        """Сохранение состояния авторизации"""
        try:
            # Копируем cookies и localStorage в основной профиль
            auth_profile_dir = "pw_profiles/auth_setup"
            main_profile_dir = "pw_profiles"
            
            logger.info("💾 Сохраняем состояние авторизации...")
            
            # Создаем основной профиль если его нет
            os.makedirs(main_profile_dir, exist_ok=True)
            
            # Копируем файлы профиля
            import shutil
            if os.path.exists(auth_profile_dir):
                # Копируем только нужные файлы профиля
                for item in os.listdir(auth_profile_dir):
                    src = os.path.join(auth_profile_dir, item)
                    dst = os.path.join(main_profile_dir, item)
                    if os.path.isdir(src):
                        if os.path.exists(dst):
                            shutil.rmtree(dst)
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                        
            logger.info("✅ Состояние авторизации сохранено")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении состояния: {e}")
            
    async def close(self):
        """Закрытие браузера"""
        try:
            if self.browser:
                await self.browser.close()
            if self.pw:
                await self.pw.stop()
            logger.info("🔒 Браузер закрыт")
        except Exception as e:
            logger.error(f"❌ Ошибка при закрытии браузера: {e}")

async def main():
    """Основная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Ручная настройка авторизации в Thumbtack')
    parser.add_argument('--headless', action='store_true', help='Запуск в headless режиме')
    args = parser.parse_args()
    
    auth_setup = AuthSetup(headless=args.headless)
    
    try:
        await auth_setup.start()
        await auth_setup.setup_auth()
        
        logger.info("🎉 Настройка авторизации завершена!")
        logger.info("🚀 Теперь можно запускать LeadProducer:")
        logger.info("   python cli/run_lead_producer.py")
        
    except KeyboardInterrupt:
        logger.info("⏹️ Прервано пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        await auth_setup.close()

if __name__ == "__main__":
    asyncio.run(main())
