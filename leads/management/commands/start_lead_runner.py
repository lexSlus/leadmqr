from django.core.management.base import BaseCommand
import asyncio
import signal
import logging
from playwright_bot.lead_producer import LeadProducer

logger = logging.getLogger("playwright_bot")

class Command(BaseCommand):
    help = "Start LeadProducer (monitor new leads and enqueue to lead_proc)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--log-level',
            type=str,
            default='INFO',
            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
            help='Set logging level'
        )

    def handle(self, *args, **options):
        # Настройка логирования
        log_level = getattr(logging, options['log_level'])
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        self.stdout.write(self.style.SUCCESS(" Starting LeadProducer..."))
        self.stdout.write(" Monitoring new leads and enqueuing to lead_proc queue")
        self.stdout.write(" Press Ctrl+C to stop")
        
        try:
            asyncio.run(self._run_producer())
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n Received shutdown signal, stopping..."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f" Error: {e}"))
            raise

    async def _run_producer(self):
        """Запуск LeadProducer с обработкой сигналов"""
        producer = LeadProducer()
        
        # Создаем задачу для producer
        producer_task = asyncio.create_task(producer.start())
        
        # Ждем завершения
        try:
            await producer_task
        except asyncio.CancelledError:
            logger.info("LeadProducer task was cancelled")
        except Exception as e:
            logger.error(f"LeadProducer error: {e}", exc_info=True)
            raise