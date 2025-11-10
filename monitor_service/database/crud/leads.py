# leads.py
"""
CRUD операции для обработанных лидов.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from ..models import ProcessedLead


async def is_lead_processed(db: AsyncSession, account_id: str, lead_key: str) -> bool:
    """Проверить, обработан ли лид."""
    result = await db.execute(
        select(ProcessedLead).where(
            ProcessedLead.account_id == account_id,
            ProcessedLead.lead_key == lead_key
        )
    )
    return result.scalar_one_or_none() is not None


async def mark_lead_as_processed(db: AsyncSession, account_id: str, lead_key: str):
    """Пометить лид как обработанный."""
    stmt = insert(ProcessedLead).values(
        account_id=account_id,
        lead_key=lead_key
    ).on_conflict_do_nothing()
    await db.execute(stmt)
    await db.commit()

