#!/usr/bin/env python3
"""
Быстрый запуск LeadProducer для тестирования
Аналог run_single_pass.py, но для LeadProducer
"""

import os
import sys
import asyncio
import logging

# Добавляем путь к проекту
sys.path.insert(0, '/Users/lex/Documents/leadmqr')

# Настройка переменных окружения
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'leadmqr.settings')

import django
django.setup()

from playwright_bot.lead_producer import LeadProducer

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("playwright_bot")

async def run_lead_producer():
    """Запуск LeadProducer для тестирования"""
    print("🚀 Запуск LeadProducer для тестирования...")
    print("📝 Мониторинг новых лидов и отправка в очередь lead_proc")
    print(" Нажмите Ctrl+C для остановки")
    print("="*50)
    
    try:
        producer = LeadProducer()
        await producer.start()
    except KeyboardInterrupt:
        print("\n Получен сигнал остановки...")
    except Exception as e:
        print(f"\n Ошибка: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Главная функция"""
    print("🧪 LeadProducer Test Runner")
    print("="*50)
    print("Этот скрипт запускает LeadProducer для тестирования:")
    print("1. Мониторит новые лиды на Thumbtack")
    print("2. Отправляет их в очередь lead_proc")
    print("3. Показывает подробные логи")
    print("="*50)
    
    try:
        asyncio.run(run_lead_producer())
    except KeyboardInterrupt:
        print("\n Получен сигнал остановки...")
    except Exception as e:
        print(f"\n Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
