#!/usr/bin/env python3
"""
Быстрый запуск run_single_pass для тестирования
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

from playwright_bot.workflows import run_single_pass

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("playwright_bot")

async def run_single_pass_test():
    """Запуск run_single_pass для тестирования"""
    print("🚀 Запуск run_single_pass для тестирования...")
    print("📝 Обработка лидов и извлечение телефонов")
    print("🛑 Нажмите Ctrl+C для остановки")
    print("="*50)
    
    try:
        result = await run_single_pass()
        print(f"✅ Результат: {result}")
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Главная функция"""
    print("🧪 Run Single Pass Test Runner")
    print("="*50)
    print("Этот скрипт запускает run_single_pass для тестирования:")
    print("1. Обрабатывает лиды")
    print("2. Извлекает телефоны")
    print("3. Показывает результат")
    print("="*50)
    
    try:
        asyncio.run(run_single_pass_test())
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
