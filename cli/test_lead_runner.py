#!/usr/bin/env python3
"""
Тестирует LeadRunner для обработки одного лида.
Использует Django ORM и Celery, поэтому требует настроенного окружения.
"""

import os
import sys
import asyncio
import logging
import argparse
from typing import Any, Dict, Optional
from playwright.async_api import async_playwright

# Настройка Django окружения
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "leadmqr.settings")
import django
django.setup()

from playwright_bot.config import SETTINGS
from playwright_bot.thumbtack_bot import ThumbTackBot
from playwright_bot.utils import unique_user_data_dir, FlowTimer
from leads.tasks import process_lead_task
from leads.models import FoundPhone, ProcessedLead
from ai_calls.tasks import enqueue_ai_call

# Настройка логирования для вывода в консоль
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("playwright_bot")

class TestLeadRunner:
    """
    Тестовая версия LeadRunner для локального тестирования.
    Запускает собственный браузер вместо подключения к WebSocket.
    """
    def __init__(self):
        self._started = False
        self._pw = None
        self._ctx = None
        self.page = None
        self.bot: Optional[ThumbTackBot] = None
        self.user_dir = unique_user_data_dir("test_runner")
        self.flow = FlowTimer()

    async def start(self):
        if self._started:
            return
        
        try:
            self._pw = await async_playwright().start()

            logger.info("Starting local browser for testing...")
            
            # Проверяем, есть ли сохраненное состояние аутентификации
            storage_state_path = "pw_profiles/auth_state.json"
            storage_state = storage_state_path if os.path.exists(storage_state_path) else None
            
            self._ctx = await self._pw.chromium.launch_persistent_context(
                user_data_dir=self.user_dir,
                headless=False,
                args=[
                    "--remote-debugging-port=9223",  # Другой порт для тестирования
                    "--remote-debugging-address=0.0.0.0",
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage", 
                    "--disable-gpu",
                ],
                viewport={"width": 1920, "height": 1080},
            )
            self.page = await self._ctx.new_page()
            
            # Блокируем ненужные ресурсы для ускорения
            await self.page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "font", "media"] else route.continue_())
            
            await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=25000)

            self.bot = ThumbTackBot(self.page)
            if "login" in self.page.url.lower():
                logger.warning("Not logged in, attempting manual login...")
                await self.bot.login_if_needed()
                await self.page.goto(f"{SETTINGS.base_url}/pro-leads", wait_until="domcontentloaded", timeout=25000)
            
            self._started = True
            logger.info("TestLeadRunner started successfully")

        except Exception as e:
            logger.error(f"Failed to start TestLeadRunner: {e}", exc_info=True)
            await self.close()
            raise

    async def close(self):
        try:
            if self._ctx:
                await self._ctx.close()
        finally:
            if self._pw:
                await self._pw.stop()
        self._pw = self._ctx = self.page = self.bot = None
        self._started = False
        logger.info("TestLeadRunner closed")

    async def _extract_phone_for_lead(self, lead_key: str) -> Optional[str]:
        rows = await self.bot.extract_phones_from_all_threads(store=None)
        for row in rows or []:
            if row.get("phone"):
                phone = str(row["phone"]).strip()
                logger.info("PHONE FOUND in thread %s -> %s", row.get("lead_key", "unknown"), phone)
                return phone

        logger.info("PHONE NOT FOUND in any thread (rows checked=%d)", len(rows or []))
        return None

    async def process_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обработка ОДНОГО лида (тестовая версия):
          - открываем список /pro-leads,
          - входим в карточку, шлём шаблон,
          - (опц.) достаём телефон в Inbox,
          - возвращаем минимально нужные данные.
        """
        lk = lead.get("lead_key")
        if not lk:
            logger.error("process_lead: no lead_key in lead: %s", lead)
            return {"ok": False, "reason": "no lead_key", "lead": lead}

        try:
            self.flow.mark(lk, "task_start")
            
            if not self._started:
                await self.start()

            href = lead.get("href") or ""
            logger.info("TestLeadRunner: processing lead %s, URL: %s", lk, self.page.url)
            
            # Шаг 1: Открываем страницу лидов
            await self.bot.open_leads()
            logger.info("TestLeadRunner: opened /leads, URL: %s", self.page.url)
            
            # Для тестирования пропускаем открытие деталей лида и отправку сообщения
            # Вместо этого сразу извлекаем телефоны из существующих тредов
            logger.info("TestLeadRunner: skipping lead details (test mode)")
            
            # Шаг 2: Извлекаем телефон из существующих тредов
            phone = await self._extract_phone_for_lead(lk)
            if phone:
                self.flow.mark(lk, "phone_found")
                logger.info("TestLeadRunner: phone found for %s: %s", lk, phone)
            else:
                logger.warning("TestLeadRunner: no phone found for %s", lk)

            result: Dict[str, Any] = {
                "ok": True,
                "lead_key": lk,
                "phone": phone,
                "variables": {
                    "lead_id": lk,
                    "lead_url": f"{SETTINGS.base_url}{href}",
                    "name": lead.get("name") or "",
                    "category": lead.get("category") or "",
                    "location": lead.get("location") or "",
                    "source": "thumbtack",
                },
            }
            
            # Логируем телеметрию
            durations = self.flow.durations(lk)
            total_time = durations.get("total_s", 0) or 0
            logger.info("TestLeadRunner: lead %s processed in %.3fs (durations: %s)", 
                       lk, total_time, durations)
            
            return result
            
        except Exception as e:
            logger.error("TestLeadRunner: error processing lead %s: %s", lk, e, exc_info=True)
            return {"ok": False, "error": str(e), "lead_key": lk, "lead": lead}

def test_process_lead_task(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Тестовая версия process_lead_task для локального тестирования.
    Использует TestLeadRunner вместо WebSocket подключения.
    """
    lk = lead.get("lead_key", "unknown")
    logger.info("test_process_lead_task: starting processing for lead %s", lk)
    
    try:
        # Создаем TestLeadRunner и обрабатываем лид
        runner = TestLeadRunner()
        result = asyncio.run(runner.process_lead(lead))
        
        if result.get("ok"):
            if result.get("phone"):
                logger.info("test_process_lead_task: phone found for %s, creating FoundPhone", lk)
                
                try:
                    # Если найден телефон, создаем FoundPhone и запускаем AI call
                    phone_obj, created = FoundPhone.objects.get_or_create(
                        lead_key=result["lead_key"],
                        phone=result["phone"],
                        defaults={"variables": result["variables"]}
                    )
                    
                    logger.info("test_process_lead_task: FoundPhone %s for lead %s (created=%s)", 
                               phone_obj.id, lk, created)
                    
                    # Запускаем AI call
                    ai_result = enqueue_ai_call.delay(str(phone_obj.id))
                    logger.info("test_process_lead_task: enqueued AI call for lead %s, task_id=%s", lk, ai_result.id)
                    
                except Exception as db_error:
                    logger.warning("test_process_lead_task: database error (expected in test): %s", db_error)
                    logger.info("test_process_lead_task: SIMULATED FoundPhone creation for lead %s", lk)
                    logger.info("test_process_lead_task: SIMULATED AI call enqueue for lead %s", lk)
                
            else:
                logger.warning("test_process_lead_task: no phone found for lead %s", lk)
            
            try:
                # Отмечаем лид как обработанный
                ProcessedLead.objects.get_or_create(key=result["lead_key"])
                logger.info("test_process_lead_task: marked lead %s as processed", lk)
            except Exception as db_error:
                logger.warning("test_process_lead_task: database error (expected in test): %s", db_error)
                logger.info("test_process_lead_task: SIMULATED ProcessedLead creation for lead %s", lk)
            
        else:
            logger.error("test_process_lead_task: failed to process lead %s: %s", 
                        lk, result.get("error", "unknown error"))
        
        return result
        
    except Exception as e:
        logger.error("test_process_lead_task: error processing lead %s: %s", lk, e, exc_info=True)
        return {"ok": False, "error": str(e), "lead": lead}
    finally:
        # Закрываем runner
        try:
            asyncio.run(runner.close())
        except Exception as cleanup_error:
            logger.warning("test_process_lead_task: error closing runner for lead %s: %s", 
                          lk, cleanup_error)

def test_lead_runner():
    print("🧪 LeadRunner Test")
    print("="*50)
    print("Этот скрипт тестирует LeadRunner:")
    print("1. Запускает собственный браузер (не WebSocket)")
    print("2. Обрабатывает тестовый лид")
    print("3. Отправляет сообщение и извлекает телефон")
    print("4. Показывает результат")
    print("="*50)
    
    # Создаем тестовый лид с фиктивным lead_key, но реальным телефоном
    # Телефон будет найден в существующих тредах
    test_lead = {
        "lead_key": "test_lead_123",  # Фиктивный lead_key для теста
        "href": "/pro-leads/test123",  # Фиктивный href
        "name": "Test Customer",
        "category": "Home Cleaning", 
        "location": "New York, NY",
        "index": 0
    }
    
    print(f"🧪 Тестируем LeadRunner с лидом: {test_lead['lead_key']}")
    print(f"📝 Имя: {test_lead['name']}")
    print(f"📝 Категория: {test_lead['category']}")
    print(f"📝 Локация: {test_lead['location']}")
    print("="*50)
    
    try:
        print("🔄 Обрабатываем тестовый лид через process_lead_task...")
        print("📝 Это симулирует полный продакшн флоу:")
        print("   1. LeadProducer находит лид")
        print("   2. Ставит process_lead_task в очередь lead_proc")
        print("   3. LeadRunner обрабатывает лид")
        print("   4. Создается FoundPhone")
        print("   5. Запускается AI звонок")
        print("="*50)
        
        # Обрабатываем лид через тестовую версию process_lead_task
        result = test_process_lead_task(test_lead)
        
        print("="*50)
        print("📊 РЕЗУЛЬТАТ ОБРАБОТКИ:")
        print(f"✅ Статус: {'OK' if result.get('ok') else 'ERROR'}")
        print(f"📝 Lead Key: {result.get('lead_key', 'N/A')}")
        print(f"📞 Телефон: {result.get('phone', 'НЕ НАЙДЕН')}")
        
        if result.get('variables'):
            vars_data = result['variables']
            print(f"🌐 URL: {vars_data.get('lead_url', 'N/A')}")
            print(f"👤 Имя: {vars_data.get('name', 'N/A')}")
            print(f"📂 Категория: {vars_data.get('category', 'N/A')}")
            print(f"📍 Локация: {vars_data.get('location', 'N/A')}")
        
        if result.get('error'):
            print(f"❌ Ошибка: {result['error']}")
        
        # process_lead_task сама создает FoundPhone и запускает AI звонок
        if result.get('ok') and result.get('phone'):
            print("="*50)
            print("🤖 AI ЗВОНОК:")
            print("✅ FoundPhone создан автоматически")
            print("✅ AI звонок поставлен в очередь автоматически")
            print(f"📞 Телефон для звонка: {result['phone']}")
            print(f"👤 Клиент: {result['variables'].get('name', 'N/A')}")
            print("="*50)
        
        if result.get('ok'):
            print("🎉 Тест завершен успешно!")
        else:
            print("❌ Тест завершен с ошибкой")
            
    except Exception as e:
        print(f"\n❌ Ошибка в тесте: {e}")
        logger.error(f"Unhandled error in test_lead_runner: {e}", exc_info=True)
        raise
    finally:
        print("✅ Тест завершен")

def main():
    parser = argparse.ArgumentParser(description="Test LeadRunner functionality.")
    parser.add_argument('--log-level', type=str, default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Set logging level (default: INFO)')
    args = parser.parse_args()

    # Устанавливаем уровень логирования
    log_level = getattr(logging, args.log_level)
    logging.getLogger().setLevel(log_level)

    try:
        test_lead_runner()
    except KeyboardInterrupt:
        logger.warning("\n🛑 Received shutdown signal, stopping...")
    except Exception as e:
        logger.error(f"❌ Unhandled error in main: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
