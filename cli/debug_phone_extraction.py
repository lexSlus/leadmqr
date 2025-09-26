#!/usr/bin/env python3
"""
Скрипт для дебага извлечения телефонных номеров из лидов Thumbtack.
Позволяет перейти на конкретный лид и протестировать извлечение телефона.
"""

import os
import sys
import asyncio
import logging
from playwright.async_api import async_playwright

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright_bot.thumbtack_bot import ThumbTackBot
from playwright_bot.config import Config

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PhoneDebugger:
    def __init__(self, headless=False):
        self.headless = headless
        self.pw = None
        self.browser = None
        self.context = None
        self.page = None
        self.bot = None
        
    async def start(self):
        """Запускаем браузер и инициализируем бота"""
        logger.info("🚀 Запуск браузера для дебага извлечения телефона...")
        
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(
            headless=self.headless,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        
        # Используем профиль авторизации
        profile_path = os.path.join(os.getcwd(), "pw_profiles", "auth_setup")
        self.context = await self.browser.new_context(
            user_data_dir=profile_path,
            viewport={'width': 1280, 'height': 720}
        )
        
        self.page = await self.context.new_page()
        self.bot = ThumbTackBot(self.page, Config())
        
        logger.info("✅ Браузер запущен")
        
    async def navigate_to_lead(self, lead_url=None):
        """Переходим на страницу лида"""
        if lead_url:
            logger.info(f"📍 Переходим на лид: {lead_url}")
            await self.page.goto(lead_url)
        else:
            logger.info("📍 Переходим на страницу лидов...")
            await self.page.goto("https://www.thumbtack.com/pro-leads")
            
        await self.page.wait_for_load_state('networkidle')
        logger.info(f"✅ Текущий URL: {self.page.url}")
        
    async def debug_phone_extraction(self):
        """Дебажим извлечение телефона"""
        logger.info("🔍 Начинаем дебаг извлечения телефона...")
        
        # Проверяем текущий URL
        current_url = self.page.url
        logger.info(f"📍 Текущий URL: {current_url}")
        
        # Проверяем, находимся ли мы на странице лида
        if "/messages/" not in current_url:
            logger.warning("⚠️  Не находимся на странице сообщений лида!")
            logger.info("💡 Перейдите на страницу сообщений лида вручную")
            logger.info("💡 Или введите URL лида при запуске скрипта")
            return None
            
        # Вызываем метод извлечения телефона
        try:
            phone = await self.bot._show_and_extract_in_current_thread()
            logger.info(f"📞 Результат извлечения телефона: {phone}")
            return phone
        except Exception as e:
            logger.error(f"❌ Ошибка при извлечении телефона: {e}")
            return None
            
    async def debug_page_elements(self):
        """Дебажим элементы страницы"""
        logger.info("🔍 Анализируем элементы страницы...")
        
        # Ищем tel: ссылки
        tel_links = await self.page.locator("a[href^='tel:']").count()
        logger.info(f"📞 Найдено tel: ссылок: {tel_links}")
        
        if tel_links > 0:
            for i in range(tel_links):
                href = await self.page.locator("a[href^='tel:']").nth(i).get_attribute("href")
                text = await self.page.locator("a[href^='tel:']").nth(i).text_content()
                logger.info(f"  📞 Tel link {i+1}: href='{href}', text='{text}'")
        
        # Ищем элементы с классом телефона
        phone_elements = await self.page.locator(".IUE7kXgIsvED2G8vml4Wu").count()
        logger.info(f"📱 Найдено элементов с классом телефона: {phone_elements}")
        
        if phone_elements > 0:
            for i in range(phone_elements):
                text = await self.page.locator(".IUE7kXgIsvED2G8vml4Wu").nth(i).text_content()
                logger.info(f"  📱 Phone element {i+1}: '{text}'")
        
        # Ищем все ссылки на странице
        all_links = await self.page.locator("a").count()
        logger.info(f"🔗 Всего ссылок на странице: {all_links}")
        
        # Ищем элементы содержащие телефонные номера
        phone_patterns = [
            r'\+\d{1,3}[\s\-]?\d{3,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}',
            r'\(\d{3}\)\s?\d{3}[\s\-]?\d{4}',
            r'\d{3}[\s\-]?\d{3}[\s\-]?\d{4}'
        ]
        
        for pattern in phone_patterns:
            elements = await self.page.locator(f"text=/{pattern}/").count()
            if elements > 0:
                logger.info(f"📞 Найдено элементов с паттерном {pattern}: {elements}")
                for i in range(min(elements, 5)):  # Показываем только первые 5
                    text = await self.page.locator(f"text=/{pattern}/").nth(i).text_content()
                    logger.info(f"  📞 Match {i+1}: '{text}'")
                    
    async def interactive_mode(self):
        """Интерактивный режим для дебага"""
        logger.info("🎮 Интерактивный режим дебага")
        logger.info("💡 Команды:")
        logger.info("  'phone' - извлечь телефон")
        logger.info("  'elements' - проанализировать элементы")
        logger.info("  'url' - показать текущий URL")
        logger.info("  'goto <url>' - перейти на URL")
        logger.info("  'quit' - выйти")
        
        while True:
            try:
                command = input("\n🔧 Введите команду: ").strip().lower()
                
                if command == 'quit':
                    break
                elif command == 'phone':
                    await self.debug_phone_extraction()
                elif command == 'elements':
                    await self.debug_page_elements()
                elif command == 'url':
                    logger.info(f"📍 Текущий URL: {self.page.url}")
                elif command.startswith('goto '):
                    url = command[5:].strip()
                    if url:
                        await self.page.goto(url)
                        await self.page.wait_for_load_state('networkidle')
                        logger.info(f"✅ Перешли на: {self.page.url}")
                    else:
                        logger.warning("⚠️  Укажите URL для перехода")
                else:
                    logger.warning("⚠️  Неизвестная команда")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
                
    async def close(self):
        """Закрываем браузер"""
        if self.browser:
            await self.browser.close()
        if self.pw:
            await self.pw.stop()
        logger.info("🔒 Браузер закрыт")

async def main():
    """Основная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Дебаг извлечения телефонов из лидов Thumbtack')
    parser.add_argument('--url', help='URL лида для тестирования')
    parser.add_argument('--headless', action='store_true', help='Запуск в headless режиме')
    parser.add_argument('--interactive', action='store_true', help='Интерактивный режим')
    
    args = parser.parse_args()
    
    debugger = PhoneDebugger(headless=args.headless)
    
    try:
        await debugger.start()
        await debugger.navigate_to_lead(args.url)
        
        if args.interactive:
            await debugger.interactive_mode()
        else:
            # Автоматический режим
            await debugger.debug_page_elements()
            await debugger.debug_phone_extraction()
            
            # Ждем немного чтобы увидеть результат
            await asyncio.sleep(5)
            
    except KeyboardInterrupt:
        logger.info("⏹️  Прервано пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        await debugger.close()

if __name__ == "__main__":
    asyncio.run(main())
