# models.py
"""
SQLAlchemy ORM модели для БД.
"""
from sqlalchemy import Column, String, Boolean, DateTime, JSON, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func
from datetime import datetime
from .base import Base


class ThumbtackAccount(Base):
    """Модель аккаунта Thumbtack."""
    __tablename__ = "thumbtack_accounts"
    
    account_id = Column(String, primary_key=True, index=True)
    email = Column(String, nullable=False, unique=True, index=True)
    password = Column(String, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    account_metadata = Column("metadata", JSONB, default={}, nullable=False)  # В БД колонка называется metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_monitored_at = Column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self):
        return f"<ThumbtackAccount(account_id={self.account_id}, email={self.email})>"


class ProcessedLead(Base):
    """Модель обработанного лида (для дедупликации)."""
    __tablename__ = "processed_leads"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    account_id = Column(String, nullable=False, index=True)
    lead_key = Column(String, nullable=False)
    processed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Уникальный индекс для пары (account_id, lead_key)
    __table_args__ = (
        Index('idx_processed_leads_account_lead', 'account_id', 'lead_key', unique=True),
    )
    
    def __repr__(self):
        return f"<ProcessedLead(account_id={self.account_id}, lead_key={self.lead_key})>"

