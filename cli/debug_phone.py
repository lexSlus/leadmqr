#!/usr/bin/env python3
"""
Дебаг извлечения телефонов - максимально близко к run_single_pass
"""

import os
import sys
import asyncio
import logging
import time
from playwright.async_api import async_playwright

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Настройка переменных окружения
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'leadmqr.settings')

import django
django.setup()

from playwright_bot.config import SETTINGS
from playwright_bot.thumbtack_bot import ThumbTackBot

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("playwright_bot")

async def debug_phone_extraction():
    """Дебаг извлечения телефонов - как в run_single_pass, но только телефоны"""
    print("🔍 Дебаг извлечения телефонов...")
    print("📞 Пропускаем лиды, сразу к извлечению телефонов")
    print("🛑 Нажмите Ctrl+C для остановки")
    print("="*50)
    
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir="./pw_profiles",  # Используем основной профиль, созданный setup_auth
            headless=False,  # НЕ headless для визуального дебага
            slow_mo=0,  # Без задержек как в оригинале
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-features=VizDisplayCompositor",
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--disable-plugins",
                "--remote-debugging-port=9222",
                "--lang=en-US",
                "--accept-lang=en-US,en;q=0.9",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor,TranslateUI",
            ],
            viewport=None,  # Как в оригинале
        )

        page = await context.new_page()
        bot = ThumbTackBot(page)
        
        try:
            # Автоматический логин если нужно
            await bot.login_if_needed()
            
            # Переходим на страницу сообщений (где есть телефоны)
            await bot.open_messages()
            print("AFTER GOTO:", page.url)
            
            # Кликаем по первому сообщению, чтобы открыть детали лида
            print("🔍 Ищем первое сообщение для открытия деталей лида...")
            threads = bot._threads()
            thread_count = await threads.count()
            print(f"📧 Найдено {thread_count} сообщений")
            
            if thread_count > 0:
                print("🖱️ Кликаем по первому сообщению...")
                await threads.first.click()
                await asyncio.sleep(2)  # Ждем загрузки деталей лида
                print("AFTER CLICK:", page.url)
            else:
                print("❌ Сообщения не найдены")
                return
            
            # Тестируем извлечение телефона с текущей страницы
            print("🔍 Тестируем извлечение телефона с текущей страницы...")
            phone = await bot._show_and_extract_in_current_thread()
            print(f"📞 Результат извлечения телефона: {phone}")
            
            # Создаем фиктивный результат для совместимости
            phones = [{"phone": phone, "lead_key": "test_lead", "href": page.url}] if phone else []
            
            # Тестируем метод _extract_phone_for_lead (БЫСТРАЯ ВЕРСИЯ)
            if phones:
                print("\n🔍 Тестируем _extract_phone_for_lead (быстрая версия)...")
                
                # Создаем быстрый объект для тестирования метода
                class FastTestRunner:
                    def __init__(self, phones_data):
                        self.phones_data = phones_data
                    
                    async def _extract_phone_for_lead(self, lead_key: str):
                        # Используем уже полученные данные вместо повторного вызова
                        for row in self.phones_data or []:
                            if (str(row.get("lead_key") or "") == str(lead_key)) and row.get("phone"):
                                phone = str(row["phone"]).strip()
                                print(f"PHONE FOUND for {lead_key} -> {phone}")
                                return phone
                        print(f"PHONE NOT FOUND for {lead_key} (rows checked={len(self.phones_data or [])})")
                        return None
                
                runner = FastTestRunner(phones)
                
                # Берем первый lead_key для теста
                first_lead_key = phones[0].get("lead_key")
                if first_lead_key:
                    print(f"🎯 Тестируем поиск телефона для lead_key: {first_lead_key}")
                    found_phone = await runner._extract_phone_for_lead(first_lead_key)
                    print(f"📱 Найденный телефон: {found_phone}")
                    
                    # Тестируем с несуществующим lead_key
                    fake_lead_key = "fake_lead_key_123"
                    print(f"🎯 Тестируем с несуществующим lead_key: {fake_lead_key}")
                    not_found_phone = await runner._extract_phone_for_lead(fake_lead_key)
                    print(f"📱 Результат для несуществующего: {not_found_phone}")
            
            return {
                "ok": True,
                "phones": phones,
                "message": "Phone extraction debug completed"
            }
            
        except KeyboardInterrupt:
            print("Получен сигнал остановки...")
        except Exception as e:
            print(f"Ошибка: {e}")
            import traceback
            traceback.print_exc()

def main():
    """Главная функция"""
    print("🔍 Phone Extraction Debug")
    print("="*50)
    print("Дебаг извлечения телефонов - как run_single_pass, но только телефоны")
    print("="*50)
    
    try:
        asyncio.run(debug_phone_extraction())
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
