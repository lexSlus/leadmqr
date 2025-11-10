# schemas.py
"""
Pydantic схемы для валидации данных.
"""
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, Dict, Any


class AccountBase(BaseModel):
    """Базовая схема аккаунта."""
    account_id: str
    email: EmailStr
    password: str
    enabled: bool = True
    metadata: Dict[str, Any] = {}  # В схеме оставляем metadata, но в БД будет account_metadata


class AccountCreate(AccountBase):
    """Схема для создания аккаунта."""
    pass


class Account(AccountBase):
    """Схема аккаунта (для чтения)."""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_monitored_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True  # SQLAlchemy 2.0 style
    
    @classmethod
    def from_orm_model(cls, obj):
        """Конвертирует ORM модель в Pydantic схему с маппингом metadata."""
        data = {
            "account_id": obj.account_id,
            "email": obj.email,
            "password": obj.password,
            "enabled": obj.enabled,
            "metadata": obj.account_metadata,  # Маппинг account_metadata -> metadata
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
            "last_monitored_at": obj.last_monitored_at,
        }
        return cls(**data)


class ProcessedLeadBase(BaseModel):
    """Базовая схема обработанного лида."""
    account_id: str
    lead_key: str


class ProcessedLead(ProcessedLeadBase):
    """Схема обработанного лида."""
    processed_at: datetime
    
    class Config:
        from_attributes = True

