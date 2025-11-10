# db_client.py
"""
Высокоуровневый клиент для работы с БД.
Обертка над database.crud для monitor_service.
"""
import logging
from typing import List
from monitor_service.database.database import AsyncSessionLocal, init_db, close_db
from monitor_service.database.crud import accounts, leads
from monitor_service.database.schemas import Account

logger = logging.getLogger(__name__)


class DBClient:
    """
    Клиент для работы с БД.
    Используется в monitor_service для получения аккаунтов и дедупликации лидов.
    """
    
    def __init__(self, db_url: str = None):
        """
        Инициализация клиента БД.
        
        Args:
            db_url: PostgreSQL connection string (опционально, берется из DATABASE_URL)
        """
        self.db_url = db_url
        if db_url:
            # Устанавливаем DATABASE_URL для database.py
            import os
            os.environ["DATABASE_URL"] = db_url
        logger.info("DBClient инициализирован")
    
    async def initialize(self):
        """
        Инициализация БД.
        
        ВНИМАНИЕ: В production не используйте create_all()!
        Используйте Alembic миграции: alembic upgrade head
        """
        # В production проверяем, что таблицы уже созданы через миграции
        # Не создаем таблицы автоматически
        logger.info("Database client initialized (use 'alembic upgrade head' to create tables)")
    
    async def close(self):
        """Закрывает соединения с БД."""
        await close_db()
    
    async def get_active_accounts(self) -> List[Account]:
        """
        Получает список активных аккаунтов для мониторинга.
        
        Returns:
            List[Account]: Список активных аккаунтов
        """
        async with AsyncSessionLocal() as db:
            accounts_list = await accounts.get_active_accounts(db)
            logger.info(f"Найдено {len(accounts_list)} активных аккаунтов")
            return accounts_list
    
    async def mark_lead_as_processed(self, account_id: str, lead_key: str) -> None:
        """
        Помечает лид как обработанный (для дедупликации).
        
        Args:
            account_id: ID аккаунта
            lead_key: Уникальный ключ лида
        """
        async with AsyncSessionLocal() as db:
            await leads.mark_lead_as_processed(db, account_id, lead_key)
            logger.debug(f"Lead {lead_key} marked as processed for account {account_id}")
    
    async def is_lead_processed(self, account_id: str, lead_key: str) -> bool:
        """
        Проверяет, был ли лид уже обработан.
        
        Args:
            account_id: ID аккаунта
            lead_key: Уникальный ключ лида
            
        Returns:
            bool: True если лид уже обработан, False иначе
        """
        async with AsyncSessionLocal() as db:
            return await leads.is_lead_processed(db, account_id, lead_key)

