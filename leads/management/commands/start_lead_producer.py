from django.core.management.base import BaseCommand
import asyncio
import signal
import logging
from playwright_bot.lead_producer import LeadProducer

logger = logging.getLogger("playwright_bot")

class Command(BaseCommand):
    help = "Start LeadProducer (monitor new leads and enqueue to lead_proc) - CLI version"

    def add_arguments(self, parser):
        parser.add_argument(
            '--log-level',
            type=str,
            default='INFO',
            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
            help='Set logging level'
        )
        parser.add_argument(
            '--cycles',
            type=int,
            default=None,
            help='Number of cycles to run (default: infinite)'
        )

    def handle(self, *args, **options):
        # Настройка логирования
        log_level = getattr(logging, options['log_level'])
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        self.stdout.write(self.style.SUCCESS("🚀 Starting LeadProducer (CLI)..."))
        self.stdout.write("📝 Monitoring new leads and enqueuing to lead_proc queue")
        self.stdout.write("🛑 Press Ctrl+C to stop")
        
        if options['cycles']:
            self.stdout.write(f"🔄 Will run for {options['cycles']} cycles")
        
        try:
            asyncio.run(self._run_producer(options['cycles']))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n🛑 Received shutdown signal, stopping..."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error: {e}"))
            raise

    async def _run_producer(self, max_cycles=None):
        """Запуск LeadProducer с ограничением циклов"""
        producer = LeadProducer()
        
        # Если указано количество циклов, модифицируем producer
        if max_cycles:
            original_loop = producer._loop
            cycle_count = 0
            
            async def limited_loop():
                nonlocal cycle_count
                while not producer.stop_evt.is_set() and cycle_count < max_cycles:
                    await original_loop()
                    cycle_count += 1
                    logger.info(f"Completed cycle {cycle_count}/{max_cycles}")
                
                if cycle_count >= max_cycles:
                    logger.info(f"Reached max cycles ({max_cycles}), stopping...")
                    producer.stop_evt.set()
            
            producer._loop = limited_loop
        
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

