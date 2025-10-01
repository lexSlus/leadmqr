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

async def extract_all_lead_data(page):
    """Извлекает все полезные данные из HTML страницы лида"""
    print("🔍 Извлекаем данные из HTML...")
    
    try:
        # Получаем HTML содержимое страницы
        html_content = await page.content()
        
        # Извлекаем телефон через регулярку (как вы уже делали)
        import re
        phone_pattern = r'tel:([+\d\s\-\(\)]+)'
        phone_matches = re.findall(phone_pattern, html_content)
        phone = phone_matches[0].strip() if phone_matches else None
        
        # Извлекаем другие полезные данные
        data = {
            "phone": phone,
            "name": None,
            "category": None,
            "location": None,
            "description": None,
            "budget": None,
            "timeline": None,
            "email": None,
            "address": None,
            "lead_id": None,
            "posted_date": None,
            "urgency": None,
            "project_size": None,
            "preferred_contact": None,
            "additional_notes": None
        }
        
        # Имя клиента - пробуем разные селекторы
        try:
            name_selectors = [
                'h1', 
                '.lead-title', 
                '[data-testid="lead-title"]',
                '.client-name',
                '.customer-name',
                'h2',
                '.title'
            ]
            for selector in name_selectors:
                name_element = await page.query_selector(selector)
                if name_element:
                    name_text = await name_element.text_content()
                    if name_text and name_text.strip():
                        data["name"] = name_text.strip()
                        break
        except:
            pass
        
        # Категория/Сервис - пробуем разные селекторы
        try:
            category_selectors = [
                '.category', 
                '.service-type', 
                '[data-testid="category"]',
                '.service-category',
                '.job-category',
                '.project-type',
                'span:has-text("Category")',
                'span:has-text("Service")'
            ]
            for selector in category_selectors:
                category_element = await page.query_selector(selector)
                if category_element:
                    category_text = await category_element.text_content()
                    if category_text and category_text.strip():
                        data["category"] = category_text.strip()
                        break
        except:
            pass
        
        # Локация - пробуем разные селекторы
        try:
            location_selectors = [
                '.location', 
                '.address', 
                '[data-testid="location"]',
                '.project-location',
                '.job-location',
                '.city',
                '.zip-code',
                'span:has-text("Location")',
                'span:has-text("Address")'
            ]
            for selector in location_selectors:
                location_element = await page.query_selector(selector)
                if location_element:
                    location_text = await location_element.text_content()
                    if location_text and location_text.strip():
                        data["location"] = location_text.strip()
                        break
        except:
            pass
        
        # Описание проекта - пробуем разные селекторы
        try:
            desc_selectors = [
                '.description', 
                '.project-description', 
                '[data-testid="description"]',
                '.job-description',
                '.project-details',
                '.details',
                'p:has-text("Description")',
                'div:has-text("Project")'
            ]
            for selector in desc_selectors:
                desc_element = await page.query_selector(selector)
                if desc_element:
                    desc_text = await desc_element.text_content()
                    if desc_text and desc_text.strip():
                        data["description"] = desc_text.strip()
                        break
        except:
            pass
        
        # Бюджет - пробуем разные селекторы
        try:
            budget_selectors = [
                '.budget', 
                '.price', 
                '[data-testid="budget"]',
                '.project-budget',
                '.estimated-cost',
                '.cost',
                'span:has-text("Budget")',
                'span:has-text("$")',
                'span:has-text("Price")'
            ]
            for selector in budget_selectors:
                budget_element = await page.query_selector(selector)
                if budget_element:
                    budget_text = await budget_element.text_content()
                    if budget_text and budget_text.strip():
                        data["budget"] = budget_text.strip()
                        break
        except:
            pass
        
        # Временные рамки - пробуем разные селекторы
        try:
            timeline_selectors = [
                '.timeline', 
                '.timeframe', 
                '[data-testid="timeline"]',
                '.project-timeline',
                '.when-needed',
                '.urgency',
                'span:has-text("Timeline")',
                'span:has-text("When")',
                'span:has-text("ASAP")'
            ]
            for selector in timeline_selectors:
                timeline_element = await page.query_selector(selector)
                if timeline_element:
                    timeline_text = await timeline_element.text_content()
                    if timeline_text and timeline_text.strip():
                        data["timeline"] = timeline_text.strip()
                        break
        except:
            pass
        
        # Email - через регулярку и селекторы
        try:
            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            email_matches = re.findall(email_pattern, html_content)
            data["email"] = email_matches[0] if email_matches else None
            
            # Также пробуем найти через селекторы
            if not data["email"]:
                email_selectors = [
                    'a[href^="mailto:"]',
                    '.email',
                    '.contact-email',
                    '[data-testid="email"]'
                ]
                for selector in email_selectors:
                    email_element = await page.query_selector(selector)
                    if email_element:
                        email_text = await email_element.text_content()
                        if email_text and '@' in email_text:
                            data["email"] = email_text.strip()
                            break
        except:
            pass
        
        # Адрес - пробуем разные селекторы
        try:
            address_selectors = [
                '.address', 
                '.full-address', 
                '[data-testid="address"]',
                '.project-address',
                '.job-address',
                '.street-address',
                'span:has-text("Address")',
                'div:has-text("Street")'
            ]
            for selector in address_selectors:
                address_element = await page.query_selector(selector)
                if address_element:
                    address_text = await address_element.text_content()
                    if address_text and address_text.strip():
                        data["address"] = address_text.strip()
                        break
        except:
            pass
        
        # Дополнительные поля - пробуем найти что-то еще
        try:
            # Ищем все текстовые элементы с полезной информацией
            all_text_elements = await page.query_selector_all('p, span, div, h1, h2, h3, h4, h5, h6')
            additional_info = []
            
            for element in all_text_elements:
                try:
                    text = await element.text_content()
                    if text and len(text.strip()) > 10 and len(text.strip()) < 200:
                        # Ищем ключевые слова
                        if any(keyword in text.lower() for keyword in ['urgent', 'asap', 'immediately', 'today', 'tomorrow']):
                            if not data["timeline"]:
                                data["timeline"] = text.strip()
                        elif any(keyword in text.lower() for keyword in ['budget', 'price', 'cost', '$', 'dollar']):
                            if not data["budget"]:
                                data["budget"] = text.strip()
                        elif any(keyword in text.lower() for keyword in ['description', 'need', 'want', 'looking for']):
                            if not data["description"]:
                                data["description"] = text.strip()
                except:
                    continue
        except:
            pass
        
        # Lead ID - из URL или метаданных
        try:
            # Извлекаем ID из URL
            url = page.url
            if '/pro-leads/' in url:
                lead_id_match = re.search(r'/pro-leads/(\d+)', url)
                if lead_id_match:
                    data["lead_id"] = lead_id_match.group(1)
        except:
            pass
        
        # Дата публикации
        try:
            date_selectors = [
                '.posted-date',
                '.date-posted',
                '.created-date',
                'span:has-text("Posted")',
                'span:has-text("Date")',
                'time'
            ]
            for selector in date_selectors:
                date_element = await page.query_selector(selector)
                if date_element:
                    date_text = await date_element.text_content()
                    if date_text and date_text.strip():
                        data["posted_date"] = date_text.strip()
                        break
        except:
            pass
        
        # Срочность
        try:
            urgency_selectors = [
                '.urgency',
                '.priority',
                '.timeline',
                'span:has-text("Urgent")',
                'span:has-text("ASAP")',
                'span:has-text("Immediate")'
            ]
            for selector in urgency_selectors:
                urgency_element = await page.query_selector(selector)
                if urgency_element:
                    urgency_text = await urgency_element.text_content()
                    if urgency_text and urgency_text.strip():
                        data["urgency"] = urgency_text.strip()
                        break
        except:
            pass
        
        # Размер проекта
        try:
            size_selectors = [
                '.project-size',
                '.job-size',
                '.scope',
                'span:has-text("Size")',
                'span:has-text("Scope")',
                'span:has-text("Large")',
                'span:has-text("Small")'
            ]
            for selector in size_selectors:
                size_element = await page.query_selector(selector)
                if size_element:
                    size_text = await size_element.text_content()
                    if size_text and size_text.strip():
                        data["project_size"] = size_text.strip()
                        break
        except:
            pass
        
        # Предпочтительный способ связи
        try:
            contact_selectors = [
                '.preferred-contact',
                '.contact-method',
                '.communication',
                'span:has-text("Contact")',
                'span:has-text("Call")',
                'span:has-text("Text")'
            ]
            for selector in contact_selectors:
                contact_element = await page.query_selector(selector)
                if contact_element:
                    contact_text = await contact_element.text_content()
                    if contact_text and contact_text.strip():
                        data["preferred_contact"] = contact_text.strip()
                        break
        except:
            pass
        
        # Дополнительные заметки
        try:
            notes_selectors = [
                '.additional-notes',
                '.notes',
                '.comments',
                '.extra-info',
                'span:has-text("Notes")',
                'span:has-text("Additional")'
            ]
            for selector in notes_selectors:
                notes_element = await page.query_selector(selector)
                if notes_element:
                    notes_text = await notes_element.text_content()
                    if notes_text and notes_text.strip():
                        data["additional_notes"] = notes_text.strip()
                        break
        except:
            pass
        
        # Выводим найденные данные
        print("📊 Найденные данные:")
        for key, value in data.items():
            if value:
                print(f"  {key}: {value}")
            else:
                print(f"  {key}: не найдено")
        
        return data
        
    except Exception as e:
        print(f"❌ Ошибка при извлечении данных: {e}")
        return {}

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
            
            # Извлекаем все полезные данные из HTML
            print("\n🔍 Извлекаем все данные из HTML страницы...")
            extracted_data = await extract_all_lead_data(page)
            
            # Отправляем Telegram уведомление если телефон найден
            if phone:
                print("\n📱 Отправляем Telegram уведомление...")
                try:
                    # Создаем тестовые данные для Telegram с полными данными
                    test_result = {
                        "variables": {
                            "name": extracted_data.get("name", "Debug Test Client"),
                            "category": extracted_data.get("category", "Phone Extraction Test"), 
                            "location": extracted_data.get("location", "Debug Location"),
                            "lead_url": page.url,
                            "description": extracted_data.get("description", ""),
                            "budget": extracted_data.get("budget", ""),
                            "timeline": extracted_data.get("timeline", ""),
                            "email": extracted_data.get("email", ""),
                            "address": extracted_data.get("address", ""),
                            "lead_id": extracted_data.get("lead_id", ""),
                            "posted_date": extracted_data.get("posted_date", ""),
                            "urgency": extracted_data.get("urgency", ""),
                            "project_size": extracted_data.get("project_size", ""),
                            "preferred_contact": extracted_data.get("preferred_contact", ""),
                            "additional_notes": extracted_data.get("additional_notes", "")
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
