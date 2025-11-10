# accounts.py
"""
CRUD операции для аккаунтов Thumbtack.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from ..models import ThumbtackAccount
from ..schemas import Account, AccountCreate


async def get_active_accounts(db: AsyncSession) -> List[Account]:
    """
    Получить список всех активных аккаунтов.
    
    Returns:
        List[Account]: Список активных аккаунтов
    """
    result = await db.execute(
        select(ThumbtackAccount).where(ThumbtackAccount.enabled == True)
    )
    accounts = result.scalars().all()
    return [Account.from_orm_model(acc) for acc in accounts]


async def get_account_by_id(db: AsyncSession, account_id: str) -> Optional[Account]:
    """
    Получить аккаунт по ID.
    
    Args:
        account_id: ID аккаунта
        
    Returns:
        Account или None если не найден
    """
    result = await db.execute(
        select(ThumbtackAccount).where(ThumbtackAccount.account_id == account_id)
    )
    account = result.scalar_one_or_none()
    return Account.from_orm_model(account) if account else None


async def get_account_by_email(db: AsyncSession, email: str) -> Optional[Account]:
    """
    Получить аккаунт по email.
    
    Args:
        email: Email аккаунта
        
    Returns:
        Account или None если не найден
    """
    result = await db.execute(
        select(ThumbtackAccount).where(ThumbtackAccount.email == email)
    )
    account = result.scalar_one_or_none()
    return Account.from_orm_model(account) if account else None


async def create_account(db: AsyncSession, account: AccountCreate) -> Account:
    """
    Создать новый аккаунт.
    
    Args:
        account: Данные для создания аккаунта
        
    Returns:
        Account: Созданный аккаунт
    """
    db_account = ThumbtackAccount(
        account_id=account.account_id,
        email=account.email,
        password=account.password,
        enabled=account.enabled,
        account_metadata=account.metadata  # В модели поле называется account_metadata
    )
    db.add(db_account)
    await db.commit()
    await db.refresh(db_account)
    return Account.from_orm_model(db_account)


async def update_account(db: AsyncSession, account_id: str, **kwargs) -> Optional[Account]:
    """
    Обновить аккаунт.
    
    Args:
        account_id: ID аккаунта
        **kwargs: Поля для обновления (email, password, enabled, metadata)
        
    Returns:
        Account или None если не найден
    """
    result = await db.execute(
        select(ThumbtackAccount).where(ThumbtackAccount.account_id == account_id)
    )
    account = result.scalar_one_or_none()
    
    if not account:
        return None
    
    # Обновляем только переданные поля
    for key, value in kwargs.items():
        if hasattr(account, key):
            setattr(account, key, value)
    
    await db.commit()
    await db.refresh(account)
    return Account.from_orm_model(account)


async def update_last_monitored_at(db: AsyncSession, account_id: str) -> None:
    """
    Обновить время последнего мониторинга аккаунта.
    
    Args:
        account_id: ID аккаунта
    """
    from datetime import datetime, timezone
    result = await db.execute(
        select(ThumbtackAccount).where(ThumbtackAccount.account_id == account_id)
    )
    account = result.scalar_one_or_none()
    
    if account:
        account.last_monitored_at = datetime.now(timezone.utc)
        await db.commit()


async def delete_account(db: AsyncSession, account_id: str) -> bool:
    """
    Удалить аккаунт.
    
    Args:
        account_id: ID аккаунта
        
    Returns:
        bool: True если удален, False если не найден
    """
    result = await db.execute(
        select(ThumbtackAccount).where(ThumbtackAccount.account_id == account_id)
    )
    account = result.scalar_one_or_none()
    
    if not account:
        return False
    
    await db.delete(account)
    await db.commit()
    return True

