#!/usr/bin/env python3
"""
Локальный запуск Lead Producer для гибридной архитектуры
"""
import logging
import time
import os
import sys
import django
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'leadmqr.settings')
django.setup()

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
log = logging.getLogger("local_producer")

def main():
    """Запускает локальный Lead Producer"""
    log.warning("🚀 ЗАПУСК ЛОКАЛЬНОГО LEAD PRODUCER")
    
    try:
        from playwright_bot.workflows import run_continuous_loop
        import asyncio
        
        log.warning("✅ Lead Producer готов к работе!")
        log.info("🚀 Используется CONTINUOUS workflow с persistent context")
        log.info("🔄 Скрипт будет крутиться постоянно и не выключаться!")
        
        # Запускаем непрерывный цикл - он сам управляет всем
        asyncio.run(run_continuous_loop())
            
    except Exception as e:
        log.error(f"💥 Критическая ошибка: {e}", exc_info=True)
        time.sleep(300)

if __name__ == "__main__":
    main()