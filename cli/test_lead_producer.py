#!/usr/bin/env python3
"""
Тест LeadProducer с ограниченным количеством циклов
Полезно для тестирования без бесконечного цикла
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

async def test_lead_producer(cycles=3):
    """Тест LeadProducer с ограниченным количеством циклов"""
    print(f"🧪 Тест LeadProducer ({cycles} циклов)...")
    print("📝 Мониторинг новых лидов и отправка в очередь lead_proc")
    print("="*50)
    
    try:
        producer = LeadProducer()
        
        # Модифицируем _loop для ограниченного количества циклов
        original_loop = producer._loop
        cycle_count = 0
        
        async def limited_loop():
            nonlocal cycle_count
            while not producer.stop_evt.is_set() and cycle_count < cycles:
                try:
                    # Выполняем один цикл мониторинга
                    await producer._renew()
                    await producer._hb()
                    
                    await producer.bot.open_leads()
                    print(f"🔍 Цикл {cycle_count + 1}: открыл /leads")
                    
                    leads = await producer.bot.list_new_leads()
                    print(f"📋 Цикл {cycle_count + 1}: найдено {len(leads)} лидов")
                    
                    cycle_count += 1
                    print(f"✅ Завершен цикл {cycle_count}/{cycles}")
                    
                    # Большая пауза между циклами для прохождения капчи
                    if cycle_count < cycles:
                        print(f"⏳ Пауза 10 секунд перед следующим циклом...")
                        await asyncio.sleep(10)
                    
                except Exception as e:
                    print(f"❌ Ошибка в цикле {cycle_count + 1}: {e}")
                    cycle_count += 1
                    if cycle_count >= cycles:
                        break
                    # Пауза даже при ошибке
                    print(f"⏳ Пауза 10 секунд после ошибки...")
                    await asyncio.sleep(10)
            
            if cycle_count >= cycles:
                print(f"🎯 Достигнуто максимальное количество циклов ({cycles}), останавливаемся...")
                producer.stop_evt.set()
        
        producer._loop = limited_loop
        
        await producer.start()
        
        print(f"🎉 Тест завершен! Обработано {cycle_count} циклов")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Тест LeadProducer')
    parser.add_argument('--cycles', type=int, default=3, help='Количество циклов (по умолчанию: 3)')
    
    args = parser.parse_args()
    
    print("🧪 LeadProducer Test Runner")
    print("="*50)
    print(f"Этот скрипт тестирует LeadProducer на {args.cycles} циклах:")
    print("1. Мониторит новые лиды на Thumbtack")
    print("2. Отправляет их в очередь lead_proc")
    print("3. Показывает подробные логи")
    print("4. Автоматически останавливается после заданного количества циклов")
    print("="*50)
    
    try:
        asyncio.run(test_lead_producer(args.cycles))
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
