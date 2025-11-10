# database.py
"""
Настройка подключения к БД и создание сессий.
"""
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from .base import Base

logger = logging.getLogger(__name__)

# PostgreSQL async URL
# Формат: postgresql+asyncpg://user:password@host:port/database
# Берется из переменной окружения
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://thumbtack:thumbtack@localhost:5432/thumbtack")

# Async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # SQL logging (включить для отладки)
    pool_pre_ping=True,  # Проверка соединения перед использованием
    pool_size=5,
    max_overflow=10
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncSession:
    """
    Dependency для получения async сессии БД.
    Использование:
        async with get_db() as db:
            # работа с БД
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """
    Инициализация БД - создание всех таблиц.
    
    ВНИМАНИЕ: В production используйте Alembic миграции!
    Эта функция только для разработки/тестирования.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.warning("Database tables created using create_all() - use Alembic migrations in production!")
        logger.info("Database tables created")


async def close_db():
    """Закрытие соединений с БД."""
    await engine.dispose()
    logger.info("Database connections closed")

