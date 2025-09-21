#!/usr/bin/env python3
"""
Запускает LeadRunner для обработки лидов из очереди lead_proc.
Использует Django ORM и Celery, поэтому требует настроенного окружения.
"""

import os
import sys
import asyncio
import logging

# Настройка Django окружения
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "leadmqr.settings")
import django
django.setup()

from playwright_bot.playwright_runner import LeadRunner

# Настройка логирования для вывода в консоль
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("playwright_bot")

async def run_lead_runner_cli():
    logger.info("🚀 Starting LeadRunner from CLI...")
    logger.info("📝 This will process leads from the lead_proc queue")
    logger.info("🔗 Connecting to browser via WebSocket (ws://celery_lead_producer:9222)")
    logger.info("🛑 Press Ctrl+C to stop")
    
    runner = LeadRunner()
    try:
        # Запускаем LeadRunner
        await runner.start()
        logger.info("✅ LeadRunner started successfully")
        
        # Держим процесс живым для обработки задач
        logger.info("⏳ Waiting for lead processing tasks...")
        logger.info("💡 LeadRunner is ready to process leads from the lead_proc queue")
        logger.info("🔄 Tasks will be processed automatically when they arrive")
        
        # Бесконечный цикл ожидания
        while True:
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        logger.info("LeadRunner task was cancelled")
    except Exception as e:
        logger.error(f"LeadRunner error: {e}", exc_info=True)
        raise
    finally:
        logger.info("🔄 Closing LeadRunner...")
        await runner.close()
        logger.info("✅ LeadRunner closed")

def main():
    try:
        asyncio.run(run_lead_runner_cli())
    except KeyboardInterrupt:
        logger.warning("\n🛑 Received shutdown signal, stopping...")
    except Exception as e:
        logger.error(f"❌ Unhandled error in main: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
