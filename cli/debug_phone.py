#!/usr/bin/env python3
"""
Дебаг извлечения телефонов - максимально близко к run_single_pass
"""

import os
import sys
import asyncio
import logging
import time
import subprocess
import signal
from playwright.async_api import async_playwright

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Настройка переменных окружения
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'leadmqr.settings')

import django
django.setup()

from playwright_bot.config import SETTINGS
from playwright_bot.thumbtack_bot import ThumbTackBot
from telegram_app.services import TelegramService

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
        # Способ 1: Подключение к уже работающему браузеру через remote debugging
        try:
            print("🔗 Пытаемся подключиться к уже работающему браузеру...")
            browser = await pw.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            print("✅ Подключились к работающему браузеру!")
        except Exception as e:
            print(f"❌ Не удалось подключиться к работающему браузеру: {e}")
            print("🚀 Запускаем новый браузер...")
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
            
            print("✅ Chromium запущен с PID:", chrome_process.pid)
            time.sleep(3)
            return True
            
        except FileNotFoundError:
            print("❌ Ни Chrome, ни Chromium не найдены!")
            return False

def stop_chrome():
    """Останавливает Chrome"""
    global chrome_process
    
    if chrome_process:
        print("🛑 Останавливаем Chrome...")
        try:
            if os.name != 'nt':
                os.killpg(os.getpgid(chrome_process.pid), signal.SIGTERM)
            else:
                chrome_process.terminate()
            chrome_process.wait(timeout=5)
            print("✅ Chrome остановлен")
        except:
            print("⚠️ Принудительно завершаем Chrome...")
            chrome_process.kill()
        chrome_process = None

async def debug_phone_extraction():
    """Дебаг извлечения телефонов - как в run_single_pass, но только телефоны"""
    print("🔍 Дебаг извлечения телефонов...")
    print("📞 Пропускаем лиды, сразу к извлечению телефонов")
    print("🛑 Нажмите Ctrl+C для остановки")
    print("="*50)
    
    # Запускаем Chrome с debug портом
    if not start_chrome_with_debug():
        print("❌ Не удалось запустить Chrome, завершаем...")
        return
    
    print("🔐 Теперь залогиньтесь в Thumbtack в открывшемся браузере...")
    print("⏳ Ждем 30 секунд для авторизации...")
    await asyncio.sleep(30)
    
    async with async_playwright() as pw:
        # Подключаемся к уже работающему браузеру через remote debugging
        try:
            print("🔗 Подключаемся к Chrome через remote debugging...")
            browser = await pw.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            print("✅ Подключились к Chrome!")
        except Exception as e:
            print(f"❌ Не удалось подключиться к Chrome: {e}")
            return
            
            print("✅ Chromium запущен с PID:", chrome_process.pid)
            time.sleep(3)
            return True
            
        except FileNotFoundError:
            print("❌ Ни Chrome, ни Chromium не найдены!")
            return False

def stop_chrome():
    """Останавливает Chrome"""
    global chrome_process
    
    if chrome_process:
        print("🛑 Останавливаем Chrome...")
        try:
            if os.name != 'nt':
                os.killpg(os.getpgid(chrome_process.pid), signal.SIGTERM)
            else:
                chrome_process.terminate()
            chrome_process.wait(timeout=5)
            print("✅ Chrome остановлен")
        except:
            print("⚠️ Принудительно завершаем Chrome...")
            chrome_process.kill()
        chrome_process = None

async def debug_phone_extraction():
    """Дебаг извлечения телефонов - как в run_single_pass, но только телефоны"""
    print("🔍 Дебаг извлечения телефонов...")
    print("📞 Пропускаем лиды, сразу к извлечению телефонов")
    print("🛑 Нажмите Ctrl+C для остановки")
    print("="*50)
    
    # Запускаем Chrome с debug портом
    if not start_chrome_with_debug():
        print("❌ Не удалось запустить Chrome, завершаем...")
        return
    
    print("🔐 Теперь залогиньтесь в Thumbtack в открывшемся браузере...")
    print("⏳ Ждем 30 секунд для авторизации...")
    await asyncio.sleep(30)
    
    async with async_playwright() as pw:
        # Подключаемся к уже работающему браузеру через remote debugging
        try:
            print("🔗 Подключаемся к Chrome через remote debugging...")
            browser = await pw.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            print("✅ Подключились к Chrome!")
        except Exception as e:
            print(f"❌ Не удалось подключиться к Chrome: {e}")
            return

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
            threads = await bot._threads()  # Добавляем await!
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
            
            # Отправляем Telegram уведомление если телефон найден
            if phone:
                print("\n📱 Отправляем Telegram уведомление...")
                try:
                    # Создаем тестовые данные для Telegram
                    test_result = {
                        "variables": {
                            "name": "Debug Test Client",
                            "category": "Phone Extraction Test", 
                            "location": "Debug Location",
                            "lead_url": page.url
                        },
                        "phone": phone,
                        "lead_key": "debug_test_phone"
                    }
                    
                    # Отправляем уведомление
                    telegram_service = TelegramService()
                    telegram_result = telegram_service.send_lead_notification(test_result)
                    
                    if telegram_result.get("success"):
                        print(f"✅ Telegram уведомление отправлено: {telegram_result.get('sent_to', 'unknown')}")
                    else:
                        print(f"❌ Telegram уведомление не отправлено: {telegram_result.get('error', 'unknown error')}")
                        
                except Exception as e:
                    print(f"❌ Ошибка при отправке Telegram: {e}")
            else:
                print("📱 Телефон не найден, Telegram уведомление не отправляется")
        
        
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
        finally:
            # Останавливаем Chrome
            stop_chrome()

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
