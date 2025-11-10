# main.py
"""
Главный файл сервиса мониторинга.
Запускает N параллельных мониторов аккаунтов.
"""
import asyncio
import logging
import signal
import sys
from typing import List

from celery import Celery
from monitor_service.config import CONFIG
from monitor_service.db_client import DBClient
from monitor_service.account_monitor import AccountMonitor
from monitor_service.browser_pool import MonitorBrowserPool

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, CONFIG.log_level.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MonitorService:
    """
    Главный сервис мониторинга.
    Управляет всеми мониторами аккаунтов.
    """
    
    def __init__(self):
        self.monitors: List[AccountMonitor] = []
        self.stop_event = asyncio.Event()
        
        # Инициализируем клиент БД
        self.db_client = DBClient(CONFIG.db_url)
        
        # Создаем пул браузеров (один браузер для всех мониторов)
        self.browser_pool = MonitorBrowserPool(
            headless=CONFIG.headless,
            slow_mo=CONFIG.slow_mo
        )
        
        # Инициализируем Celery как клиент (для отправки задач)
        self.celery_app = Celery(
            "monitor_service",
            broker=CONFIG.celery_broker_url
        )
        self.celery_app.conf.task_serializer = "json"
        self.celery_app.conf.accept_content = ["json"]
        self.celery_app.conf.result_serializer = "json"
        
        logger.info("MonitorService инициализирован")
    
    async def start(self):
        """Запускает сервис мониторинга."""
        logger.info("=" * 60)
        logger.info("🔍 СЕРВИС МОНИТОРИНГА - ЗАПУСК")
        logger.info("=" * 60)
        
        try:
            # 1. Инициализируем БД (таблицы должны быть созданы через Alembic миграции)
            await self.db_client.initialize()
            
            # 2. Запускаем браузер (один для всех мониторов)
            await self.browser_pool.start()
            logger.info("Браузер запущен, готов к созданию контекстов")
            
            # 3. Получаем список активных аккаунтов из БД
            try:
                accounts = await self.db_client.get_active_accounts()
            except Exception as e:
                logger.error(f"Ошибка получения аккаунтов из БД: {e}", exc_info=True)
                logger.warning("Использую fallback на переменные окружения")
                accounts = self._get_accounts_from_env()
            
            if not accounts:
                logger.error("Нет активных аккаунтов для мониторинга!")
                logger.error("Добавьте аккаунты в БД или установите переменные окружения")
                return
            
            logger.info(f"Найдено {len(accounts)} аккаунтов для мониторинга")
            
            # 4. Создаем мониторы для каждого аккаунта
            # Каждый монитор будет использовать один браузер, но свой контекст
            for account in accounts:
                monitor = AccountMonitor(account, self.celery_app, self.browser_pool, self.db_client)
                self.monitors.append(monitor)
                logger.info(f"Создан монитор для аккаунта: {account.account_id} ({account.email})")
            
            # 5. Запускаем все мониторы параллельно
            logger.info(f"Запуск {len(self.monitors)} мониторов (все используют один браузер)...")
            
            tasks = [monitor.start() for monitor in self.monitors]
            
            # Ждем завершения всех задач (или остановки)
            try:
                await asyncio.gather(*tasks)
            except asyncio.CancelledError:
                logger.info("Получен сигнал остановки")
            
        except Exception as e:
            logger.error(f"Критическая ошибка в MonitorService: {e}", exc_info=True)
        finally:
            await self.stop()
    
    async def stop(self):
        """Останавливает все мониторы и браузер."""
        logger.info("Остановка всех мониторов...")
        
        # Останавливаем все мониторы
        stop_tasks = [monitor.stop() for monitor in self.monitors]
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)
        
        # Закрываем соединения с БД
        await self.db_client.close()
        
        # Останавливаем браузер
        await self.browser_pool.stop()
        
        logger.info("Сервис мониторинга остановлен")
        self.stop_event.set()
    
    def _get_accounts_from_env(self):
        """Fallback: получает список аккаунтов из переменных окружения."""
        from monitor_service.database.schemas import Account
        import os
        
        accounts = []
        
        # Один основной аккаунт
        email = os.getenv("TT_EMAIL")
        password = os.getenv("TT_PASSWORD")
        account_id = os.getenv("TT_ACCOUNT_ID", "account_1")
        
        if email and password:
            # Создаем Pydantic модель (Account из database.schemas)
            accounts.append(Account(
                account_id=account_id,
                email=email,
                password=password,
                enabled=True,
                created_at=None,  # Для fallback не требуется
                updated_at=None,
                last_monitored_at=None
            ))
        
        return accounts


# Глобальный экземпляр сервиса
monitor_service: MonitorService = None


def signal_handler(signum, frame):
    """Обработчик сигналов для корректной остановки."""
    logger.info(f"Получен сигнал {signum}, остановка...")
    if monitor_service:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(monitor_service.stop())
            else:
                loop.run_until_complete(monitor_service.stop())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(monitor_service.stop())


async def main():
    """Главная функция."""
    global monitor_service
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Создаем и запускаем сервис
    monitor_service = MonitorService()
    
    try:
        await monitor_service.start()
    except KeyboardInterrupt:
        logger.info("Получен KeyboardInterrupt")
    finally:
        await monitor_service.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Завершение работы...")
        sys.exit(0)

